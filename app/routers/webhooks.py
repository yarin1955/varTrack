from flask import Blueprint, current_app,request, jsonify
from app.middlewares.webhooks import validate_route_param
from ..models.datasource import DataSource
from ..models.git_platform import GitPlatform
from ..utils.handlers.webhooks import WebhooksHandler
from app.tasks.main_agent import webhook_handler
from ..utils.interfaces.isource import ISource

bp = Blueprint('webhooks', __name__)

@bp.post("<string:platform>/<string:datasource>")
@validate_route_param(param_name='platform', transform_func=GitPlatform.get_registry_keys)
@validate_route_param(param_name='datasource', transform_func=DataSource.get_registry_keys)
def handler_webhooks(platform, datasource):

    json_payload = request.get_json()
    raw_payload = request.data.decode('utf-8')
    headers=dict(request.headers)

    platform_config = current_app.config.get(platform)
    if not platform_config:
        return jsonify({'status': 'error', 'message': 'Server configuration error'}), 500

    try:
        platform_instance = GitPlatform.create(**platform_config)
        signature = headers.get(platform_instance.git_scm_signature)

        if not WebhooksHandler.verify_signature(platform_instance.secret, raw_payload, signature):
            return jsonify({'status': 'unauthorized', 'message': 'Invalid signature'}), 401

    except Exception as e:
        return jsonify({'status': 'error', 'message': 'Verification failed'}), 500

    task = webhook_handler.apply_async(
        args=[platform, datasource, raw_payload, json_payload, headers])

    return jsonify({
        'status': 'accepted',
        'task_id': task.id,
        'message': 'Webhook received and queued for processing'
    }), 202
