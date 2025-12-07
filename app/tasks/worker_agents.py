import asyncio
from datetime import datetime
from typing import Dict, Any, Union
from flask import current_app
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

@celery_app.task(name='app.worker_agent_task', bind=True)
def worker_agent_task(self):
    random_number = "7"
    print(f"Worker Agent [{self.request.id}] generated: {random_number}")
    return {
        'task_id': self.request.id,
        'random_number': random_number,
        'agent_type': 'worker'
    }


@celery_app.task(name='app.data_manager', bind=True, queue='worker_agents')
def data_manager(self, platform_config: dict, datasource_config: dict, items_dict: dict, role_dict: dict):
    """
    Processes the NormalizedPush/NormalizedPR object.
    OPTIMIZED: Fetches all file contents concurrently before processing.
    """

    platform_name = platform_config.get('name', 'unknown')
    datasource_name = datasource_config.get('name', 'unknown')

    # 1. Reconstruct Objects
    try:
        role = Role(**role_dict)

        # Reconstruct Commits
        commits_data = items_dict.get('commits', [])
        reconstructed_commits = []
        for c in commits_data:
            if isinstance(c.get('timestamp'), str):
                c['timestamp'] = datetime.fromisoformat(c['timestamp'])
            reconstructed_commits.append(NormalizedCommit(**c))

        items_dict['commits'] = reconstructed_commits

        # Identify Object Type
        obj_type = items_dict.pop('_type', None)

        if obj_type == 'NormalizedPR' or 'base_branch' in items_dict:
            actionable_items = NormalizedPR(**items_dict)
            before_sha = items_dict.get('base_sha')
        else:
            actionable_items = NormalizedPush(**items_dict)
            before_sha = items_dict.get('before')

    except Exception as e:
        print(f"❌ Error reconstructing objects: {e}")
        return {'status': 'error', 'message': f"Deserialization failed: {e}"}

    # 2. Initialize Platform
    try:
        platform_loader(platform_name, GitPlatform)
        platform_instance = PlatformFactory.create(**platform_config)
    except Exception as e:
        print(f"❌ Error initializing platform '{platform_name}': {e}")
        return {'status': 'error', 'message': str(e)}

    # 3. Initialize & Connect to Datasource
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

    # 4. Prepare Logic
    actionable_items.sort_commits(reverse=True)
    all_files = actionable_items.get_all_changed_files()
    repo_name = actionable_items.repository
    ref = actionable_items.branch if hasattr(actionable_items, 'branch') else actionable_items.head_branch

    print(f"Processing {len(all_files)} potential files in {repo_name}")

    # --- PHASE 1: IDENTIFY WORK ---
    files_to_process = []

    for file_path in all_files:
        # A. Match File
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
            print(f"   ⚠️ Could not find commit for file {file_path}")
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

            current_matches = find_key_iterative(current_obj, "varTrack")
            previous_matches = find_key_iterative(previous_obj, "varTrack")

            current_flattened_data = flatten_dfs(current_matches)
            previous_flattened_data = flatten_dfs(previous_matches)

            # E. Compare
            state_comparison = compare_states(current_data=current_flattened_data, old_data=previous_flattened_data)

            payload = {
                "key": match_context.get('key'),
                "env": match_context.get('env'),
                "file": file_path,
                "last_commit": last_commit_hash,
                "changes": state_comparison
            }

            # F. Insert
            ds_adapter.insert(payload)
            processed_count += 1

        except Exception as e:
            print(f"❌ Error processing file {file_path}: {e}")
            continue

    return {
        'status': 'success',
        'total_matched_files': processed_count,
        'total_scanned_files': len(all_files)
    }
