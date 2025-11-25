from flask import Blueprint, current_app,request, jsonify
import asyncio

from app.utils.handlers.webhooks import WebhooksHandler
from app.middlewares.webhooks import validate_route_param
from app.utils.factories.datasource_factory import DataSourceFactory
from app.utils.factories.platform_factory import PlatformFactory
from ..business_logic.compare_states import compare_states
from ..business_logic.json_pathmap import flatten_dfs, find_key_iterative
from ..tasks.main_agent import webhook_handler
from ..utils.commands.storage_invoker import StorageInvoker
from ..utils.factories.ds_adapter_factory import DSAdapterFactory
from ..utils.handlers.file_formats import FileFormatsHandler

bp = Blueprint('webhooks', __name__)

@bp.post("<string:platform>/<string:datasource>")
@validate_route_param(param_name='platform', transform_func=PlatformFactory.get_available_platforms)
@validate_route_param(param_name='datasource', transform_func=DataSourceFactory.get_available_datasources)
def handler_webhooks(platform, datasource):
    # webhook_handler.delay(
    #     platform= platform,
    #     datasource= datasource,
    #     raw_payload=request.data.decode('utf-8'),
    #     signature=request.headers.get('X-Hub-Signature-256'),
    #     event_type=request.headers.get('X-GitHub-Event')
    # )
    raw_payload = request.data.decode('utf-8')
    signature = request.headers.get('X-Hub-Signature-256')
    event_type = request.headers.get('X-GitHub-Event')
    #main agent
    secret = current_app.config.get(platform).get("secret", None)
    if not WebhooksHandler.verify_signature(secret, raw_payload, signature):
        return jsonify({'error': 'Invalid signature'}), 401

    platform_instance = PlatformFactory.create(**current_app.config.get(platform))

    destined_file= current_app.config.get(f"{platform}::{datasource}").get("fileName")
    if WebhooksHandler.is_push_event(event_type):
        commits = WebhooksHandler.handle_push_event(request, platform_instance, destined_file)

    elif WebhooksHandler.is_pr_event(event_type):
        commits = WebhooksHandler.handle_pr_event(request)

    current_file= asyncio.run(platform_instance.get_file_from_commit(commits.repo_name, commits.get("first"), destined_file))
    old_file= asyncio.run(platform_instance.get_file_from_commit(commits.repo_name, commits.get("last"), destined_file))

    current_file= FileFormatsHandler.convert_string_to_json(current_file)
    old_file= FileFormatsHandler.convert_string_to_json(current_file)

    current_data= find_key_iterative(current_file, "varTrack")
    old_data= find_key_iterative(old_file, "varTrack")

    current_data= flatten_dfs(current_data)
    old_data= flatten_dfs(old_data)

    idk= compare_states(current_data=current_data, old_data=old_data)

    datasource_instance = DataSourceFactory.create(**current_app.config.get(datasource))
    print(f"xxxxxx {datasource_instance}")
    ds_adapter_instance= DSAdapterFactory.create(config=datasource_instance)

    ds_adapter_instance.connect()
    #
    # invoker = StorageInvoker()
    # sassa= compare_json_strings()
    # insert_cmd = InsertCommand(redis_strategy, "user:1", "John Doe")
    # update_cmd = InsertCommand(redis_strategy, "user:1", "John Doe")
    # delete_cmd = InsertCommand(redis_strategy, "user:1", "John Doe")

    return f"{idk}"




@bp.post('/admin')
def admin_route():
    return 'Admin area'