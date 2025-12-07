from flask import Blueprint, request, jsonify
from ..tasks.main_agent import main_agent_task
from ..celery_app import celery

bp = Blueprint('tasks', __name__)


# HTTP Endpoint to trigger main agent
@bp.route('/trigger-agent', methods=['POST'])
def trigger_agent():
    """
    HTTP endpoint to trigger the main agent.

    Request JSON:
        {
            "num_workers": 3  // number of workers to spawn (default: 1)
        }

    Response:
        {
            "status": "success",
            "message": "Main agent task triggered",
            "task_id": "abc-123-...",
            "check_result_url": "/tasks/result/abc-123-...",
            "full_result_url": "/tasks/full-result/abc-123-..."
        }
    """
    data = request.get_json() or {}
    num_workers = data.get('num_workers', 1)

    # Validation
    if not isinstance(num_workers, int) or num_workers < 1:
        return jsonify({
            'status': 'error',
            'message': 'num_workers must be a positive integer'
        }), 400

    # Trigger main agent task asynchronously
    task = main_agent_task.apply_async(args=[num_workers])

    return jsonify({
        'status': 'success',
        'message': f'Main agent task triggered with {num_workers} worker(s)',
        'task_id': task.id,
        'check_result_url': f'/tasks/result/{task.id}',
        'full_result_url': f'/tasks/full-result/{task.id}'
    }), 202


@bp.route('/result/<task_id>', methods=['GET'])
def get_result(task_id):
    """
    Check the status and result of a task (quick, non-blocking).

    If the task is a main agent, also includes current state of all workers.
    """
    task = celery.AsyncResult(task_id)

    if task.state == 'PENDING':
        response = {
            'status': 'pending',
            'task_id': task_id,
            'message': 'Task is waiting to be executed'
        }
    elif task.state == 'STARTED':
        response = {
            'status': 'running',
            'task_id': task_id,
            'message': 'Task is currently executing'
        }
    elif task.state == 'SUCCESS':
        result = task.result

        # If this is a main agent task, check worker states (non-blocking)
        if isinstance(result, dict) and 'worker_task_ids' in result:
            worker_states = []
            completed_count = 0

            for worker_id in result['worker_task_ids']:
                worker_task = celery.AsyncResult(worker_id)

                worker_info = {
                    'task_id': worker_id,
                    'state': worker_task.state,
                }

                if worker_task.state == 'SUCCESS':
                    worker_info['result'] = worker_task.result
                    completed_count += 1
                elif worker_task.state == 'FAILURE':
                    worker_info['error'] = str(worker_task.info)

                worker_states.append(worker_info)

            result['worker_states'] = worker_states
            result['workers_completed'] = completed_count
            result['workers_total'] = len(result['worker_task_ids'])

        response = {
            'status': 'success',
            'task_id': task_id,
            'result': result
        }
    elif task.state == 'FAILURE':
        response = {
            'status': 'failed',
            'task_id': task_id,
            'error': str(task.info)
        }
    else:
        response = {
            'status': task.state.lower(),
            'task_id': task_id
        }

    return jsonify(response)


@bp.route('/full-result/<task_id>', methods=['GET'])
def get_full_result(task_id):
    """
    Wait for main task AND all worker tasks to complete, then return full results.
    This endpoint blocks until all tasks are done or timeout is reached.

    Query parameters:
        ?timeout=30  // max seconds to wait (default: 30)
    """
    import time

    timeout = int(request.args.get('timeout', 30))
    start_time = time.time()

    task = celery.AsyncResult(task_id)

    # Wait for main task to complete
    while task.state in ['PENDING', 'STARTED']:
        if time.time() - start_time > timeout:
            return jsonify({
                'status': 'timeout',
                'task_id': task_id,
                'message': f'Main task did not complete within {timeout}s'
            }), 408

        time.sleep(0.2)
        task = celery.AsyncResult(task_id)

    if task.state == 'FAILURE':
        return jsonify({
            'status': 'failed',
            'task_id': task_id,
            'error': str(task.info)
        }), 500

    result = task.result

    # If main agent task, wait for all workers to complete
    if isinstance(result, dict) and 'worker_task_ids' in result:
        worker_results = []

        for worker_id in result['worker_task_ids']:
            worker_task = celery.AsyncResult(worker_id)

            # Wait for this worker to complete
            while worker_task.state in ['PENDING', 'STARTED']:
                if time.time() - start_time > timeout:
                    worker_results.append({
                        'task_id': worker_id,
                        'state': 'TIMEOUT',
                        'error': f'Worker did not complete within {timeout}s'
                    })
                    break

                time.sleep(0.2)
                worker_task = celery.AsyncResult(worker_id)
            else:
                # Worker completed (SUCCESS or FAILURE)
                if worker_task.state == 'SUCCESS':
                    worker_results.append(worker_task.result)
                elif worker_task.state == 'FAILURE':
                    worker_results.append({
                        'task_id': worker_id,
                        'state': 'FAILURE',
                        'error': str(worker_task.info)
                    })

        result['worker_results'] = worker_results
        result['all_completed'] = True

        # Remove worker_task_ids since we now have full results
        del result['worker_task_ids']

    return jsonify({
        'status': 'success',
        'task_id': task_id,
        'result': result
    })


@bp.route('/batch-result', methods=['POST'])
def get_batch_results():
    """
    Check status of multiple tasks at once.

    Request JSON:
        {
            "task_ids": ["abc-123", "def-456", ...]
        }
    """
    data = request.get_json() or {}
    task_ids = data.get('task_ids', [])

    if not task_ids or not isinstance(task_ids, list):
        return jsonify({
            'status': 'error',
            'message': 'task_ids must be a non-empty array'
        }), 400

    results = []
    for task_id in task_ids:
        task = celery.AsyncResult(task_id)

        task_info = {
            'task_id': task_id,
            'state': task.state,
        }

        if task.state == 'SUCCESS':
            task_info['result'] = task.result
        elif task.state == 'FAILURE':
            task_info['error'] = str(task.info)

        results.append(task_info)

    return jsonify({
        'status': 'success',
        'total': len(task_ids),
        'results': results
    })
