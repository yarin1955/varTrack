from collections import defaultdict

from pydantic import TypeAdapter
from app.models.bundle import Bundle
from app.models.git_platform import GitPlatform
from app.pipeline.core import Source
from app.utils.interfaces.isource import ISource


def initializer(data: Bundle):
    config_data = TypeAdapter(Bundle).validate_python(data)

    rules_by_platform = defaultdict(list)

    for rule in config_data.rules:
        rules_by_platform[rule.platform].append(rule)

    available_platforms = GitPlatform.get_registry_keys()

    for platform_conf in config_data.platforms:
        if platform_conf.name not in available_platforms:
            print(f"Warning: Platform '{platform_conf.name}' not found")
            continue

        platform_rules = rules_by_platform.get(platform_conf.name)
        if not platform_rules:
            continue

        platform_instance = ISource.create(**platform_conf.model_dump())
        for rule in platform_rules:
            if not rule.repositories:
                continue

            platform_instance.setup_webhooks(
                config_data.schema_registry,
                rule.repositories,
                rule.datasource,
                rule.excludeRepositories
            )