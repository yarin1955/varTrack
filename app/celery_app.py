import json
import dataclasses
from datetime import datetime
from enum import Enum  # <--- Import Enum
from celery import Celery
from kombu.serialization import register
from pydantic import BaseModel


class TaskJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, Enum):    # <--- Add this block
            return obj.value         # Returns the string value (e.g. "added")
        if isinstance(obj, BaseModel):
            return obj.model_dump()
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def task_json_dumps(obj):
    return json.dumps(obj, cls=TaskJSONEncoder)


def task_json_loads(obj):
    return json.loads(obj)


register(
    'task-json',
    task_json_dumps,
    task_json_loads,
    content_type='application/json',
    content_encoding='utf-8'
)

celery = Celery(__name__)


def init_celery(app):
    celery_conf = app.config.get("celery", {})

    base_config = {
        'task_serializer': 'task-json',
        'result_serializer': 'task-json',
        'accept_content': ['task-json', 'json'],
        'timezone': 'UTC',
        'enable_utc': True,
        'task_acks_late': True,
        'task_reject_on_worker_lost': True,
        'worker_prefetch_multiplier': 1,
        'task_time_limit': 900,
        'task_soft_time_limit': 840,
        'task_routes': {
            'app.main_agent_task': {'queue': 'main_agent'},
            'app.worker_agent_task': {'queue': 'worker_agents'},
            'app.webhook_handler': {'queue': 'main_agent'},
            'app.data_manager': {'queue': 'worker_agents'},
        },
        'workers': {
            'main': {
                'worker_max_tasks_per_child': 1000,  # Recycle occasionally to be safe
                'worker_concurrency': 10,
                'worker_pool': 'threads',
                'worker_queues': ['main_agent'],
            },
            'worker': {
                'worker_max_tasks_per_child': 100,
                'worker_concurrency': 20,
                'worker_pool': 'threads',
                'worker_queues': ['worker_agents']
            }
        }
    }

    celery.conf.update({**base_config, **celery_conf})

    class AppContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = AppContextTask
    app.extensions["celery"] = celery
    return celery