from flask import Flask

from .business_logic.initializer import initializer
from .routers.webhooks import bp as webhooks_bp
from .routers.self_healing import bp as self_healing_bp

from .routers.tasks import bp as tasks_bp
from .celery_app import init_celery
from .tasks.watcher_agent import reconciliation_service


def create_app(config_data: dict | None = None) -> Flask:
    app = Flask(__name__)

    app.config["SCHEMA_REGISTRY"] = config_data["schema_registry"]

    for platform in config_data.get("platforms", []):
        app.config[platform["name"]] = platform

    for datasource in config_data.get("datasources", []):
        app.config[datasource["name"]] = datasource

    for rule in config_data.get("rules", []):
        key = f"{rule['platform']}::{rule['datasource']}"
        app.config[key] = rule

    # Celery config from JSON (if present)
    if "celery" in config_data:
        app.config["celery"] = config_data["celery"]

    # Blueprints
    app.register_blueprint(webhooks_bp, url_prefix="/webhooks")
    app.register_blueprint(tasks_bp, url_prefix="/tasks")

    app.register_blueprint(self_healing_bp, url_prefix="/self-healing")

    # Start the background engine
    if config_data.get("self_healing", {}).get("enabled", False):
        reconciliation_service.start()

    init_celery(app)

    return app