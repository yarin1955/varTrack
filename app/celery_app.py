from celery import Celery

celery = Celery(__name__)

def init_celery(app):
    celery_conf = app.config.get("celery")

    base_config = {
        # Base configuration
        'task_serializer': 'json',
        'accept_content': ['json'],
        'result_serializer': 'json',
        'timezone': 'UTC',
        'enable_utc': True,
        'task_routes': {
            'app.main_agent_task': {'queue': 'main_agent'},
            'app.worker_agent_task': {'queue': 'worker_agents'},
        },
        'worker_prefetch_multiplier': 1,

        # Worker type configurations
        'workers': {
            'main': {
                'worker_max_tasks_per_child': None,  # Never restart (always exists)
                'worker_concurrency': 1,  # Single worker
                'worker_queues': ['main_agent'],  # Only listen to main_agent queue
            },
            'worker': {
                'worker_max_tasks_per_child': 1,  # Restart after each job (cleanup)
                'worker_concurrency': 4,  # Multiple workers
                'worker_queues': ['worker_agents'],  # Only listen to worker_agents queue
            }
        }
    }
    # celery.conf.update(celery_conf)
    # celery_app.conf.update({**base_config, **worker_config})
    celery.conf.update({**base_config, **celery_conf})


    class AppContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = AppContextTask
    app.extensions["celery"] = celery
    return celery