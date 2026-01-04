from flask import Blueprint, request, jsonify, current_app

from app.tasks.watcher_agent import reconciliation_service

bp = Blueprint('self_healing', __name__)

@bp.route('/detect-drift', methods=['POST'])
def detect_drift():
    # Logic to create temporary manager from request params and call .reconcile(dry_run=True)
    return jsonify({"status": "success", "drift_count": 0})

@bp.route('/reconcile', methods=['POST'])
def reconcile_now():
    # Logic to trigger immediate full reconciliation
    return jsonify({"status": "success"})

@bp.route('/validate-key', methods=['POST'])
def validate_key():
    # Logic to check one specific key
    return jsonify({"in_sync": True})

@bp.route('/server/status', methods=['GET'])
def server_status():
    return jsonify(reconciliation_service.get_status())

@bp.route('/server/enable', methods=['POST'])
def server_enable():
    data = request.json
    reconciliation_service.enable_schedule(data['repository'], data['branch'])
    return jsonify({"status": "enabled"})