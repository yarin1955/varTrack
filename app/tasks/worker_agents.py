import asyncio
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
from app.utils.handlers.file_formats import FileFormatsHandler
from app.utils.handlers.webhooks import WebhooksHandler
from app.business_logic.compare_states import compare_states
from app.business_logic.json_pathmap import flatten_dfs, find_key_iterative
from app.models.datasources import load_module as ds_loader
from app.models.datasources_adapters import load_module as ds_adapter_loader
from app.models.git_platforms import load_module as platform_loader

# --- NEW IMPORTS FOR CONFIG ARCHITECTURE ---
from app.business_logic.config_merger import resolve_config
from app.utils.preset_resolver import PresetResolver


@celery_app.task(name='app.data_manager', bind=True, queue='worker_agents')
def data_manager(self, platform_config: dict, datasource_config: dict, items_dict: dict, role_dict: dict):
    """
    Processes the NormalizedPush/NormalizedPR object.

    Architecture Update:
    1. Reconstructs Event Objects.
    2. connects to Platform.
    3. Fetches Repository Config & Presets (Multi-tenancy).
    4. Merges Configuration layers.
    5. connects to Datasource.
    6. Processes files based on the FINAL merged configuration.
    """

    platform_name = platform_config.get('name', 'unknown')
    datasource_name = datasource_config.get('name', 'unknown')

    # ---------------------------------------------------------
    # 1. Reconstruct Objects (Event Data)
    # ---------------------------------------------------------
    try:
        # Reconstruct Commits
        commits_data = items_dict.get('commits', [])
        reconstructed_commits = []
        for c in commits_data:
            if isinstance(c.get('timestamp'), str):
                c['timestamp'] = datetime.fromisoformat(c['timestamp'])
            reconstructed_commits.append(NormalizedCommit(**c))

        items_dict['commits'] = reconstructed_commits

        # Identify Object Type and Target Commit
        obj_type = items_dict.pop('_type', None)

        commit_sha = None
        repo_name = items_dict.get('repository')

        if obj_type == 'NormalizedPR' or 'base_branch' in items_dict:
            actionable_items = NormalizedPR(**items_dict)
            before_sha = items_dict.get('base_sha')
            commit_sha = items_dict.get('head_sha')
        else:
            actionable_items = NormalizedPush(**items_dict)
            before_sha = items_dict.get('before')
            commit_sha = items_dict.get('after')

        if not commit_sha:
            # Fallback if SHA is missing (rare), use HEAD/main or first commit
            commit_sha = actionable_items.commits[0].hash if actionable_items.commits else "HEAD"

    except Exception as e:
        print(f"Error reconstructing objects: {e}")
        return {'status': 'error', 'message': f"Deserialization failed: {e}"}

    # ---------------------------------------------------------
    # 2. Initialize Platform (Required for fetching config)
    # ---------------------------------------------------------
    try:
        platform_loader(platform_name, GitPlatform)
        platform_instance = PlatformFactory.create(**platform_config)
    except Exception as e:
        print(f"Error initializing platform '{platform_name}': {e}")
        return {'status': 'error', 'message': str(e)}

    # ---------------------------------------------------------
    # 3. Configuration & Multi-Tenancy Logic (The Renovate Logic)
    # ---------------------------------------------------------
    print(f"⚙️  Resolving configuration for {repo_name} at {commit_sha}...")

    # A. Fetch Repo-Level Config (.vartrack.json)
    repo_config_data = {}
    try:
        # We run the async fetch synchronously here
        repo_config_content = asyncio.run(platform_instance.get_file_from_commit(
            repo_name, commit_sha, ".vartrack.json"
        ))

        if repo_config_content:
            repo_config_data = json.loads(repo_config_content)
            print(f"✅ Found .vartrack.json in {repo_name}")
        else:
            # Try alternate name if needed, or just log
            print(f"ℹ️  No .vartrack.json found. Using global defaults.")

    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in .vartrack.json for {repo_name}. Ignoring repo config.")
    except Exception as e:
        print(f"⚠️ Error fetching repo config: {e}")

    # B. Resolve Presets
    # Combine 'extends' from Global (role_dict) and Repo (repo_config_data)
    # Repo extends are appended to Global extends
    global_extends = role_dict.get('extends', [])
    repo_extends = repo_config_data.get('extends', [])

    # Ensure lists are lists
    if isinstance(global_extends, str): global_extends = [global_extends]
    if isinstance(repo_extends, str): repo_extends = [repo_extends]

    all_extends = global_extends + repo_extends

    resolved_presets = []
    if all_extends:
        print(f"📥 Resolving presets: {all_extends}")
        try:
            resolver = PresetResolver(platform_instance)
            # Fetch all presets in parallel/sequence
            resolved_presets = asyncio.run(resolver.resolve_all(all_extends))
        except Exception as e:
            print(f"❌ Error resolving presets: {e}")
            # Depending on policy, we might fail here or continue with partial config
            # For now, we continue
            pass

    # C. Merge Configurations (Global -> Presets -> Repo)
    try:
        # role_dict passed from Main Agent serves as the Global Config
        final_role_dict = resolve_config(role_dict, repo_config_data, resolved_presets)

        # Instantiate Role (Pydantic handles defaults)
        role = Role(**final_role_dict)
        print(f"✅ Configuration Loaded. Strategy: {role.fileName if role.fileName else 'FilePathMap'}")

    except ValidationError as e:
        print(f"❌ Configuration Validation Failed: {e}")
        return {'status': 'error', 'message': f"Invalid configuration: {e}"}
    except Exception as e:
        print(f"❌ Unexpected Error merging config: {e}")
        return {'status': 'error', 'message': f"Config merge failed: {e}"}

    # ---------------------------------------------------------
    # 4. Initialize & Connect to Datasource
    # ---------------------------------------------------------
    try:
        ds_loader(datasource_name, DataSource)
        ds_adapter_loader(datasource_name, DataSourceAdapter)
        datasource_instance = DataSourceFactory.create(**datasource_config)
        ds_adapter = DSAdapterFactory.create(config=datasource_instance)
        ds_adapter.connect()
        print(f"✅ Connected to datasource: {datasource_name}")
    except Exception as e:
        print(f"❌ Error connecting to datasource '{datasource_name}': {e}")
        return {'status': 'error', 'message': str(e)}

    # ---------------------------------------------------------
    # 5. Prepare Logic (Processing)
    # ---------------------------------------------------------
    actionable_items.sort_commits(reverse=True)
    all_files = actionable_items.get_all_changed_files()

    ref = actionable_items.branch if hasattr(actionable_items, 'branch') else actionable_items.head_branch

    print(f"Processing {len(all_files)} potential files in {repo_name}")

    # --- PHASE 1: IDENTIFY WORK ---
    files_to_process = []

    for file_path in all_files:
        # A. Match File using the FINAL Role object
        match_context = WebhooksHandler._match_file_to_role(file_path, ref, role)
        if not match_context:
            continue

        # B. Find Last Commit
        last_commit_hash = None
        for commit in actionable_items.commits:
            if commit.has_file_changed(file_path):
                last_commit_hash = commit.hash
                break

        if not last_commit_hash:
            print(f"Could not find commit for file {file_path}")
            continue

        files_to_process.append({
            'file_path': file_path,
            'last_commit_hash': last_commit_hash,
            'match_context': match_context
        })

    if not files_to_process:
        return {'status': 'success', 'message': 'No matching files found to process'}

    # --- PHASE 2: CONCURRENT FETCHING ---
    async def fetch_all_contents():
        tasks = []
        for item in files_to_process:
            # Task for Current Content
            tasks.append(platform_instance.get_file_from_commit(
                repo_name, item['last_commit_hash'], item['file_path']
            ))

            # Task for Previous Content (if applicable)
            if before_sha:
                tasks.append(platform_instance.get_file_from_commit(
                    repo_name, before_sha, item['file_path']
                ))
            else:
                # Dummy task to keep indices aligned
                async def _noop():
                    return None

                tasks.append(_noop())

        return await asyncio.gather(*tasks)

    try:
        # Execute all network calls in parallel
        print(f"🚀 Fetching content for {len(files_to_process)} files concurrently...")
        fetch_results = asyncio.run(fetch_all_contents())
    except Exception as e:
        print(f"❌ Error during concurrent fetch: {e}")
        return {'status': 'error', 'message': f"Fetch failed: {e}"}

    # --- PHASE 3: PROCESS & INSERT ---
    processed_count = 0

    # fetch_results contains [file1_curr, file1_prev, file2_curr, file2_prev, ...]
    for i, item in enumerate(files_to_process):
        file_path = item['file_path']
        match_context = item['match_context']
        last_commit_hash = item['last_commit_hash']

        # Extract results based on index
        current_file_content = fetch_results[i * 2]
        previous_file_content = fetch_results[(i * 2) + 1]

        print(f" -> Processing: {file_path} (Env: {match_context.get('env')})")

        try:
            # D. Parse & Flatten
            current_obj = "{}"
            if current_file_content:
                current_obj = FileFormatsHandler.convert_string_to_json(current_file_content)

            previous_obj = "{}"
            if previous_file_content:
                previous_obj = FileFormatsHandler.convert_string_to_json(previous_file_content)

            # Note: We might want to make "varTrack" root key configurable via Role/Preset in the future
            target_root_key = "varTrack"

            current_matches = find_key_iterative(current_obj, target_root_key)
            previous_matches = find_key_iterative(previous_obj, target_root_key)

            # If the root key isn't found, find_key_iterative might return None or empty
            # Depending on implementation, we handle it:
            if not current_matches:
                print(f"⚠️ Key '{target_root_key}' not found in {file_path}")
                # We treat it as empty, or skip depending on policy.
                # Assuming empty means "deleted" if it existed before.
                current_flattened_data = {}
            else:
                current_flattened_data = flatten_dfs(current_matches)

            if not previous_matches:
                previous_flattened_data = {}
            else:
                previous_flattened_data = flatten_dfs(previous_matches)

            # E. Compare
            state_comparison = compare_states(current_data=current_flattened_data, old_data=previous_flattened_data)

            # F. Upsert/Delete
            upsert_data = state_comparison['added'] | {k: v['new'] for k, v in state_comparison['changed'].items()}

            if upsert_data:
                # Add metadata to the data before upserting if needed (e.g. env, repo)
                # Currently simple key-value upsert
                ds_adapter.upsert(upsert_data)

            if state_comparison['deleted']:
                ds_adapter.delete(state_comparison['deleted'])

            processed_count += 1

        except Exception as e:
            print(f"❌ Error processing file {file_path}: {e}")
            continue

    return {
        'status': 'success',
        'total_matched_files': processed_count,
        'total_scanned_files': len(all_files),
        'config_strategy': role.fileName or "Map"
    }