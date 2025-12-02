from app.celery_app import celery as celery_app
from .worker_agents import worker_agent_task
from flask import current_app, jsonify
from app.utils.handlers.webhooks import WebhooksHandler
from app.utils.factories.datasource_factory import DataSourceFactory
from app.utils.factories.platform_factory import PlatformFactory
from ..business_logic.compare_states import compare_states
from ..business_logic.json_pathmap import flatten_dfs, find_key_iterative
from ..utils.class_loader import import_from_string
from ..utils.commands.insert_command import InsertCommand
from ..utils.commands.storage_invoker import StorageInvoker
from ..utils.factories.ds_adapter_factory import DSAdapterFactory
from ..utils.handlers.file_formats import FileFormatsHandler
import asyncio
import json

@celery_app.task(name='app.main_agent_task', bind=True)
def main_agent_task(self, num_workers=1):
    """Main agent that creates worker agents without blocking on .get()."""

    worker_task_ids = []

    # Create worker agent(s) asynchronously and collect task IDs
    for i in range(num_workers):
        res = worker_agent_task.apply_async()
        worker_task_ids.append(res.id)

    # Do NOT call res.get() here – let HTTP layer handle waiting/aggregation
    return {
        'main_task_id': self.request.id,
        'agent_type': 'main',
        'workers_created': num_workers,
        'worker_task_ids': worker_task_ids,
    }


@celery_app.task(name='app.webhook_handler', bind=True, queue='main_agent')
def webhook_handler(self, platform, datasource, raw_payload, json_data, headers):
    """
    Handle incoming webhooks, fetch files, compare states, and update datasource.
    """
    # 1. Initialize Platform
    try:
        platform_cls = import_from_string(f"app.models.git_platforms.{platform}")
        platform_config = current_app.config.get(platform)
        if not platform_config:
            raise ValueError(f"Configuration for platform '{platform}' not found.")

        platform_instance = PlatformFactory.create(**platform_config)
    except Exception as e:
        print(f"❌ Error initializing platform: {e}")
        return {'status': 'error', 'message': str(e)}

    # 2. Verify Signature
    event_type_header = platform_instance.event_type_header
    signature_header = platform_instance.git_scm_signature

    event_type = headers.get(event_type_header)
    signature = headers.get(signature_header)

    print(f"Event type: {event_type}")
    print(f"Signature: {signature}")

    secret = platform_config.get("secret")
    if not WebhooksHandler.verify_signature(secret, raw_payload, signature):
        return jsonify({'error': 'Invalid signature'}), 401

    # 3. Import Datasource Classes
    try:
        datasource_cls = import_from_string(f"app.models.datasources.{datasource}")
        ds_adapter_cls = import_from_string(f"app.models.datasources_adapters.{datasource}")
    except Exception as e:
        print(f"❌ Error importing datasource classes: {e}")
        return {'status': 'error', 'message': str(e)}

    # 4. Get Role Configuration
    role_config_key = f"{platform}::{datasource}"
    role_config = current_app.config.get(role_config_key)
    if not role_config:
        print(f"⚠️ No role configuration found for {role_config_key}")
        return {'status': 'ignored', 'reason': 'Role config missing'}

    # 5. Normalize Payload and Get Actionable Items
    actionable_items = []
    if WebhooksHandler.is_push_event(event_type):
        actionable_items = WebhooksHandler.handle_push_event(json_data, platform_cls, role_config)
    elif WebhooksHandler.is_pr_event(event_type):
        actionable_items = WebhooksHandler.handle_pr_event(raw_payload)

    if not actionable_items:
        return {'status': 'ignored', 'reason': 'No matching files found in commits'}

    # 6. Initialize Datasource Connection
    try:
        datasource_config = current_app.config.get(datasource)
        datasource_instance = DataSourceFactory.create(**datasource_config)
        print(f"Datasource instance: {datasource_instance}")

        ds_adapter = DSAdapterFactory.create(config=datasource_instance)
        ds_adapter.connect()
    except Exception as e:
        print(f"❌ Error initializing datasource: {e}")
        return {'status': 'error', 'message': str(e)}

    invoker = StorageInvoker()
    processed_count = 0

    # 7. Process Each Actionable Item
    for item in actionable_items:
        destined_file = item.get('file_path')
        repo_name = item.get('repository')
        # Use .get() to avoid KeyError. Fallback to commit_hash if after_sha isn't present.
        after_sha = item.get('after_sha') or item.get('commit_hash')
        before_sha = item.get('before_sha')

        print(f"Processing changes for file: {destined_file}")

        try:
            # Fetch Current Content
            current_file_content = None
            if after_sha:
                current_file_content = asyncio.run(platform_instance.get_file_from_commit(
                    repo_name,
                    after_sha,
                    destined_file
                ))

            # Fetch Previous Content (if exists)
            previous_file_content = None
            if before_sha:
                previous_file_content = asyncio.run(platform_instance.get_file_from_commit(
                    repo_name,
                    before_sha,
                    destined_file
                ))

            # Convert to JSON String (Handling YAML/XML/etc conversion)
            current_obj = "{}"
            if current_file_content:
                current_obj = FileFormatsHandler.convert_string_to_json(current_file_content)

            previous_obj = "{}"
            if previous_file_content:
                previous_obj = FileFormatsHandler.convert_string_to_json(previous_file_content)

            current_section = find_key_iterative(current_obj, "varTrack")
            previous_section = find_key_iterative(previous_obj, "varTrack")

            # Flatten
            current_flattened_data = flatten_dfs(current_section)
            previous_flattened_data = flatten_dfs(previous_section)

            # Compare
            state_comparison = compare_states(current_data=current_flattened_data, old_data=previous_flattened_data)

            datasource_config = current_app.config.get(datasource)
            datasource_instance = DataSourceFactory.create(**datasource_config)
            print(f"Datasource instance: {datasource_instance}")

            ds_adapter = DSAdapterFactory.create(config=datasource_instance)
            invoker = StorageInvoker()
            ds_adapter.connect()
            cmd= InsertCommand(ds_adapter, state_comparison['changed']['value']['new'])
            invoker.execute_command(cmd)

        except Exception as e:
            print(f"❌ Error processing file {destined_file}: {e}")
            # traceback.print_exc()
            continue

    return {
        'status': 'success',
        'processed_files': processed_count,
        'total_actionable': len(actionable_items)
    }

