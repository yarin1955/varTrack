import json
from datetime import datetime
from pydantic import ValidationError

from app.celery_app import celery as celery_app
from app.models.datasource import DataSource
from app.models.ds_adapter import DataSourceAdapter
from app.models.git_platform import GitPlatform
from app.models.role import Role
from app.utils.normalized_pr import NormalizedPR
from app.utils.normalized_push import NormalizedPush
from app.utils.normalized_commit import NormalizedCommit
from app.utils.factories.datasource_factory import DataSourceFactory
from app.utils.factories.ds_adapter_factory import DSAdapterFactory
from app.utils.factories.platform_factory import PlatformFactory
from app.utils.handlers.webhooks import WebhooksHandler
from app.models.datasources import load_module as ds_loader
from app.models.datasources_adapters import load_module as ds_adapter_loader
from app.models.git_platforms import load_module as platform_loader
from app.business_logic.config_merger import resolve_config
from app.utils.preset_resolver import PresetResolver

# 🚀 NEW PIPELINE IMPORTS
from app.pipeline.sources.git_source import GitSource
from app.pipeline.transforms.parser import ContentParser
from app.pipeline.transforms.flattener import Flattenizer
from app.pipeline.transforms.differ import DiffExploder
from app.pipeline.sinks.mongo_sink import MongoSink


@celery_app.task(name='app.data_manager', bind=True, queue='worker_agents')
def data_manager(self, platform_config: dict, datasource_config: dict, items_dict: dict, role_dict: dict):
    """
    The Pipeline Engine.
    Executes the 'Source -> Transform -> Sink' flow following SeaTunnel architecture.
    """
    platform_name = platform_config.get('name', 'unknown')
    datasource_name = datasource_config.get('name', 'unknown')
    repo_name = items_dict.get('repository')

    print(f"🔧 [Engine] Starting job for {repo_name}...")

    # =========================================================================
    # PHASE 1: SETUP & CONFIGURATION (The "Job Plan")
    # =========================================================================

    # 1. Reconstruct Event Objects
    try:
        # Fix timestamps
        commits_data = items_dict.get('commits', [])
        for c in commits_data:
            if isinstance(c.get('timestamp'), str):
                c['timestamp'] = datetime.fromisoformat(c['timestamp'])
        items_dict['commits'] = [NormalizedCommit(**c) for c in commits_data]

        # Determine Event Type
        obj_type = items_dict.pop('_type', None)
        commit_sha = None
        before_sha = None

        if obj_type == 'NormalizedPR' or 'base_branch' in items_dict:
            actionable_items = NormalizedPR(**items_dict)
            before_sha = items_dict.get('base_sha')
            commit_sha = items_dict.get('head_sha')
        else:
            actionable_items = NormalizedPush(**items_dict)
            before_sha = items_dict.get('before')
            commit_sha = items_dict.get('after')

        # Fallback for SHA
        if not commit_sha:
            commit_sha = actionable_items.commits[0].hash if actionable_items.commits else "HEAD"

    except Exception as e:
        print(f"❌ Error reconstructing objects: {e}")
        return {'status': 'error', 'message': f"Deserialization failed: {e}"}

    # 2. Initialize Platform (Needed for Config Fetching + Source)
    try:
        platform_loader(platform_name, GitPlatform)
        platform_instance = PlatformFactory.create(**platform_config)
    except Exception as e:
        return {'status': 'error', 'message': f"Platform init failed: {e}"}

    # 3. Resolve Configuration (Global -> Presets -> Repo)
    # (This logic remains here because it decides *what* files to fetch)
    repo_config_data = {}
    try:
        # GEVEVT CHANGE: Removed asyncio.run()
        repo_config_content = platform_instance.get_file_from_commit(
            repo_name, commit_sha, ".vartrack.json"
        )
        if repo_config_content:
            repo_config_data = json.loads(repo_config_content)
    except Exception:
        pass  # Ignore missing config

    # Merge Presets
    global_extends = role_dict.get('extends', [])
    repo_extends = repo_config_data.get('extends', [])
    if isinstance(global_extends, str): global_extends = [global_extends]
    if isinstance(repo_extends, str): repo_extends = [repo_extends]

    all_extends = global_extends + repo_extends
    resolved_presets = []
    if all_extends:
        try:
            resolver = PresetResolver(platform_instance)
            # GEVENT CHANGE: Removed asyncio.run()
            resolved_presets = resolver.resolve_all(all_extends)
        except Exception:
            pass

    # Final Config Merge
    try:
        final_role_dict = resolve_config(role_dict, repo_config_data, resolved_presets)
        role = Role(**final_role_dict)
    except ValidationError as e:
        return {'status': 'error', 'message': f"Invalid config: {e}"}

    # =========================================================================
    # PHASE 2: INITIALIZE PIPELINE COMPONENTS
    # =========================================================================

    # 1. Identify Files to Process (The "Split Enumerator")
    actionable_items.sort_commits(reverse=True)
    all_files = actionable_items.get_all_changed_files()
    ref = getattr(actionable_items, 'branch', getattr(actionable_items, 'head_branch', 'HEAD'))

    files_to_process = []
    for file_path in all_files:
        match_context = WebhooksHandler._match_file_to_role(file_path, ref, role)
        if not match_context:
            continue

        # Find the specific commit that changed this file
        last_commit_hash = next(
            (c.hash for c in actionable_items.commits if c.has_file_changed(file_path)),
            commit_sha
        )

        files_to_process.append({
            'file_path': file_path,
            'last_commit_hash': last_commit_hash,
            'match_context': match_context
        })

    if not files_to_process:
        return {'status': 'success', 'message': 'No matching files found'}

    # 2. Connect to Datasource (The Connection)
    try:
        ds_loader(datasource_name, DataSource)
        ds_adapter_loader(datasource_name, DataSourceAdapter)

        # Create Config Instance (contains is_upsert_enable)
        datasource_instance = DataSourceFactory.create(**datasource_config)

        # Create Adapter & Connect
        ds_adapter = DSAdapterFactory.create(config=datasource_instance)
        ds_adapter.connect()
    except Exception as e:
        return {'status': 'error', 'message': f"Datasource connection failed: {e}"}

    # 3. Instantiate Components
    # Source
    source = GitSource(
        platform=platform_instance,
        repo_name=repo_name,
        files_to_process=files_to_process,
        before_sha=before_sha
    )

    # Transforms
    parser = ContentParser()
    flattener = Flattenizer(root_key="varTrack")
    differ = DiffExploder()

    # Sink
    # We unwrap the adapter to get the raw collection for the Sink
    # (Assuming MongoAdapter stores it in _collection)
    if hasattr(ds_adapter, '_collection'):
        raw_collection = ds_adapter._collection
    else:
        # Fallback or error if adapter structure is different
        raise RuntimeError("Adapter does not expose '_collection'")

    sink = MongoSink(
        collection=raw_collection,
        is_upsert_enable=getattr(datasource_instance, 'is_upsert_enable', False),
        batch_size=1000
    )

    # =========================================================================
    # PHASE 3: EXECUTE PIPELINE
    # =========================================================================
    print(f"🚀 [Engine] Pipeline running: Git -> Parse -> Flatten -> Diff -> Mongo")

    processed_files = 0
    total_rows_written = 0

    try:
        # A. SOURCE: Parallel Read
        # GEVENT CHANGE: Removed asyncio.run()
        file_results = source.read()

        for item in file_results:
            try:
                # B. TRANSFORMS: Chain of Responsibility

                # 1. Parse (String -> Dict)
                curr_dict = parser.process(item['current'])
                prev_dict = parser.process(item['previous'])

                # 2. Flatten (Dict -> Flat Dict)
                curr_flat = flattener.process(curr_dict)
                prev_flat = flattener.process(prev_dict)

                # 3. Diff (States -> Row Stream)
                rows = differ.process(
                    current=curr_flat,
                    previous=prev_flat,
                    metadata=item['metadata']
                )

                # C. SINK: Write to Buffer
                for row in rows:
                    sink.write(row)
                    total_rows_written += 1

                processed_files += 1

            except Exception as e:
                print(f"⚠️ [Engine] Skipped file {item['file_path']}: {e}")

        # D. SINK: Final Flush
        sink.flush()
        print(f"✅ [Engine] Job Complete. Processed {processed_files} files, {total_rows_written} rows.")

    except Exception as e:
        print(f"❌ [Engine] Pipeline Critical Error: {e}")
        return {'status': 'error', 'message': str(e)}

    return {
        'status': 'success',
        'processed_files': processed_files,
        'config_strategy': role.fileName or "Map"
    }