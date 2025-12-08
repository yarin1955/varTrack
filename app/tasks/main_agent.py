from app.celery_app import celery as celery_app
from .worker_agents import data_manager
from flask import current_app
from app.utils.handlers.webhooks import WebhooksHandler
from app.utils.factories.platform_factory import PlatformFactory
from ..models.git_platform import GitPlatform
from app.models.git_platforms import load_module as platform_loader
from ..models.role import Role
from dataclasses import asdict


@celery_app.task(name='app.webhook_handler', bind=True, queue='main_agent')
def webhook_handler(self, platform, datasource, raw_payload, json_payload, headers):
    try:
        # Load Platform Class & Config
        platform_cls = platform_loader(f"{platform}", GitPlatform)
        platform_config = current_app.config.get(platform)
        if not platform_config:
            raise ValueError(f"Configuration for platform '{platform}' not found.")

        platform_instance = PlatformFactory.create(**platform_config)
    except Exception as e:
        print(f"❌ Error initializing platform: {e}")
        return {'status': 'error', 'message': str(e)}

    # Load Role Config (Dict)
    role_config = current_app.config.get(f"{platform}::{datasource}")
    if not role_config:
        return {'status': 'ignored', 'reason': 'Role config missing'}

    # Handle Webhook
    try:
        # Instantiate temporary Role object for validation inside handle_webhook
        actionable_items = WebhooksHandler.handle_webhook(platform=platform_instance, raw_payload=raw_payload,
            json_payload=json_payload,  # Pass parsed JSON if your handler uses it
            headers=headers,
            role=role_config
        )
    except Exception as e:
        print(f"❌ Error handling webhook: {e}")
        return {'status': 'error', 'message': str(e)}

    if not actionable_items:
        return {'status': 'ignored', 'reason': 'No matching files found in commits'}

    try:
        # Resolve specific Role for Repo
        role_config_key = f"{platform}::{datasource}"
        role_config = current_app.config.get(role_config_key)
        if not role_config:
            print(f"⚠️ No role configuration found for {role_config_key}")
            return {'status': 'ignored', 'reason': 'Role config missing'}

        base_role = Role(**role_config)
        role = base_role.resolve_role_for_repo(actionable_items.repository)
    except Exception as e:
        print(f"❌ Error initializing Role: {e}")
        return {'status': 'error', 'message': str(e)}

    # --- SERIALIZATION FIX ---
    # Convert objects to Dicts manually to satisfy the default JSON serializer
    try:
        items_payload = asdict(actionable_items)  # Converts NormalizedPush/PR to dict
        role_payload = role.model_dump()  # Converts Pydantic Role to dict

        # Add a hint about the type so the worker knows what to reconstruct
        items_payload['_type'] = 'NormalizedPR' if hasattr(actionable_items, 'base_branch') else 'NormalizedPush'

    except Exception as e:
        print(f"❌ Error serializing payload: {e}")
        return {'status': 'error', 'message': f"Serialization error: {e}"}

    datasource_config = current_app.config.get(datasource)
    # Dispatch to Data Manager with DICTIONARIES
    task = data_manager.apply_async(
        args=[platform_config, datasource_config, items_payload, role_payload]
    )

    return {'status': 'processing', 'task_id': task.id}

