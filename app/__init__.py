from flask import Flask

from .business_logic.initializer import initializer
from .routers.webhooks import bp as webhooks_bp
from .routers.tasks import bp as tasks_bp
from .celery_app import init_celery

def create_app(config_data: dict | None = None) -> Flask:
    app = Flask(__name__)

    app.config["SCHEMA_REGISTRY"] = config_data["schema_registry"]

    for platform in config_data.get("platforms", []):
        app.config[platform["name"]] = platform

    for datasource in config_data.get("datasources", []):
        app.config[datasource["name"]] = datasource

    for role in config_data.get("roles", []):
        key = f"{role['platform']}::{role['datasource']}"
        app.config[key] = role

    # Celery config from JSON (if present)
    if "celery" in config_data:
        app.config["celery"] = config_data["celery"]

    # Blueprints
    app.register_blueprint(webhooks_bp, url_prefix="/webhooks")
    app.register_blueprint(tasks_bp, url_prefix="/tasks")

    init_celery(app)

    return app