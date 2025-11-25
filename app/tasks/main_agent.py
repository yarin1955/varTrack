from pydantic.v1.schema import schema

from app.celery_app import celery as celery_app
from .worker_agents import worker_agent_task
from ..utils.handlers.webhooks import WebhooksHandler
from flask import current_app, jsonify


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

@celery_app.task(name='app.webhook_handler', bind=True)
def webhook_handler(self, platform, datasource, raw_payload, signature, event_type):
    secret = (current_app.config.get(platform))["secret"]
    if not WebhooksHandler.verify_signature(secret, raw_payload, signature):
        return jsonify({'error': 'Invalid signature'}), 401

    if WebhooksHandler.is_push_event(event_type):
        commits= WebhooksHandler.handle_push_event(raw_payload)

    elif WebhooksHandler.is_pr_event(event_type):
        commits= WebhooksHandler.handle_pr_event(raw_payload)

     # _get_file_sync
    # grep
    # compare schema
    # commapare states, previcous and current
    # command update

