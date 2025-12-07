from collections import defaultdict

from pydantic import TypeAdapter
from app.models.bundle import Bundle
from app.utils.factories.platform_factory import PlatformFactory


def initializer(data: Bundle):
    config_data = TypeAdapter(Bundle).validate_python(data)

    roles_by_platform = defaultdict(list)

    for role in config_data.roles:
        roles_by_platform[role.platform].append(role)

    available_platforms = PlatformFactory.get_available_platforms()

    for platform_conf in config_data.platforms:
        if platform_conf.name not in available_platforms:
            print(f"Warning: Platform '{platform_conf.name}' not found")
            continue

        platform_roles = roles_by_platform.get(platform_conf.name)
        if not platform_roles:
            continue

        platform_instance = PlatformFactory.create(**platform_conf.model_dump())

        for role in platform_roles:
            if not role.repositories:
                continue

            platform_instance.setup_webhooks(
                config_data.schema_registry,
                role.repositories,
                role.datasource,
                role.excludeRepositories
            )