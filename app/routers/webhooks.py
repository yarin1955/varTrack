from flask import Blueprint, current_app,request, jsonify
from app.middlewares.webhooks import validate_route_param
from app.utils.factories.datasource_factory import DataSourceFactory
from app.utils.factories.platform_factory import PlatformFactory
from ..tasks.main_agent import webhook_handler


bp = Blueprint('webhooks', __name__)

@bp.post("<string:platform>/<string:datasource>")
@validate_route_param(param_name='platform', transform_func=PlatformFactory.get_available_platforms)
@validate_route_param(param_name='datasource', transform_func=DataSourceFactory.get_available_datasources)
def handler_webhooks(platform, datasource):

    json_data = request.get_json()
    raw_payload = request.data.decode('utf-8')
    headers=dict(request.headers)

    task = webhook_handler.apply_async(
        args=[platform, datasource, raw_payload, json_data, headers])

    return jsonify({
        'status': 'accepted',
        'task_id': task.id,
        'message': 'Webhook received and queued for processing'
    }), 202
