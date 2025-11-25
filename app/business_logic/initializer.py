from pydantic import TypeAdapter
from app.models.bundle import Bundle
from app.utils.factories.platform_factory import PlatformFactory


def initializer(data: Bundle):

    config_data_adapter = TypeAdapter(Bundle)
    config_data: Bundle = config_data_adapter.validate_python(data)

    role_lookup = {role.platform: role for role in config_data.roles if hasattr(role, 'platform') and role.platform}

    available_platforms = PlatformFactory.get_available_platforms()

    for platform in config_data.platforms:
        if platform.name not in available_platforms:
            print(f"Warning: Platform '{platform.name}' not found in registry")
            continue

        matching_role = role_lookup.get(platform.name)
        repos_array = getattr(matching_role, 'repositories', []) if matching_role else []
        datasource = getattr(matching_role, 'datasource', None) if matching_role else None

        # This will now lazy load the platform class automatically
        platform_instance = PlatformFactory.create(**platform.model_dump())
        platform_instance.setup_webhooks(config_data.schema_registry, repos_array, datasource)