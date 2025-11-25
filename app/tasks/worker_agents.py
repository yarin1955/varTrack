from app.celery_app import celery as celery_app


@celery_app.task(name='app.worker_agent_task', bind=True)
def worker_agent_task(self):
    """Worker agent that generates a random number"""
    random_number = "7"
    print(f"Worker Agent [{self.request.id}] generated: {random_number}")
    return {
        'task_id': self.request.id,
        'random_number': random_number,
        'agent_type': 'worker'
    }
