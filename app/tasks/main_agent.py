from app.celery_app import celery as celery_app
from .worker_agents import data_manager
from flask import current_app
from app.utils.handlers.webhooks import WebhooksHandler

from dataclasses import asdict

from ..models.git_platform import GitPlatform
from ..models.rule import Rule


@celery_app.task(name='app.webhook_handler', bind=True, queue='main_agent')
def webhook_handler(self, platform, datasource, raw_payload, json_payload, headers):
    try:
        # Load Platform Class & Config
        platform_config = current_app.config.get(platform)
        if not platform_config:
            raise ValueError(f"Configuration for platform '{platform}' not found.")

        platform_instance = GitPlatform.create(**platform_config)
    except Exception as e:
        print(f"❌ Error initializing platform: {e}")
        return {'status': 'error', 'message': str(e)}

    # Load rule Config (Dict)
    rule_config = current_app.config.get(f"{platform}::{datasource}")
    if not rule_config:
        return {'status': 'ignored', 'reason': 'rule config missing'}

    # Handle Webhook
    try:
        # Instantiate temporary rule object for validation inside handle_webhook
        actionable_items = WebhooksHandler.handle_webhook(platform=platform_instance, raw_payload=raw_payload,
            json_payload=json_payload,  # Pass parsed JSON if your handler uses it
            headers=headers,
            rule=rule_config
        )
    except Exception as e:
        print(f"❌ Error handling webhook: {e}")
        return {'status': 'error', 'message': str(e)}

    if not actionable_items:
        return {'status': 'ignored', 'reason': 'No matching files found in commits'}

    try:
        # Resolve specific rule for Repo
        rule_config_key = f"{platform}::{datasource}"
        rule_config = current_app.config.get(rule_config_key)
        if not rule_config:
            print(f"⚠️ No rule configuration found for {rule_config_key}")
            return {'status': 'ignored', 'reason': 'rule config missing'}

        base_rule = Rule(**rule_config)
        rule = base_rule.resolve_rule_for_repo(actionable_items.repository)
    except Exception as e:
        print(f"❌ Error initializing rule: {e}")
        return {'status': 'error', 'message': str(e)}

    # --- SERIALIZATION FIX ---
    # Convert objects to Dicts manually to satisfy the default JSON serializer
    try:
        items_payload = asdict(actionable_items)  # Converts NormalizedPush/PR to dict
        rule_payload = rule.model_dump()  # Converts Pydantic rule to dict

        # Add a hint about the type so the worker knows what to reconstruct
        items_payload['_type'] = 'NormalizedPR' if hasattr(actionable_items, 'base_branch') else 'NormalizedPush'

    except Exception as e:
        print(f"❌ Error serializing payload: {e}")
        return {'status': 'error', 'message': f"Serialization error: {e}"}

    datasource_config = current_app.config.get(datasource)
    # Dispatch to Data Manager with DICTIONARIES
    task = data_manager.apply_async(
        args=[platform_config, datasource_config, items_payload, rule_payload]
    )

    return {'status': 'processing', 'task_id': task.id}

