from app.celery_app import celery as celery_app
from .worker_agents import worker_agent_task, data_manager
from flask import current_app
from app.utils.handlers.webhooks import WebhooksHandler
from app.utils.factories.platform_factory import PlatformFactory
from ..models.datasource import DataSource
from ..models.ds_adapter import DataSourceAdapter
from ..models.git_platform import GitPlatform
from app.models.datasources import load_module as ds_loader
from app.models.datasources_adapters import load_module as ds_adapter_loader
from app.models.git_platforms import load_module as platform_loader

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
def webhook_handler(self, platform, datasource, raw_payload, json_payload, headers):

    try:
        platform_cls = platform_loader(f"{platform}", GitPlatform)
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

    secret = platform_config.get("secret")

    # 3. Import Datasource Classes
    try:
        datasource_cls = ds_loader(f"{datasource}", DataSource)
        ds_adapter_cls = ds_adapter_loader(f"{datasource}", DataSourceAdapter)
    except Exception as e:
        print(f"❌ Error importing datasource classes: {e}")
        return {'status': 'error', 'message': str(e)}

    # 4. Get Role Configuration
    role_config_key = f"{platform}::{datasource}"
    role_config = current_app.config.get(role_config_key)
    if not role_config:
        print(f"⚠️ No role configuration found for {role_config_key}")
        return {'status': 'ignored', 'reason': 'Role config missing'}


    actionable_items= WebhooksHandler.handle_webhook(platform, raw_payload, signature, event_type, secret, role_config)

    if not actionable_items:
        return {'status': 'ignored', 'reason': 'No matching files found in commits'}

    task = data_manager.apply_async(
        args=[platform, datasource, actionable_items, event_type])

    return ""

