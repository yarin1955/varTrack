from typing import List, Any
from pydantic import BaseModel, ConfigDict, field_validator

from app.models.datasource import DataSource
from app.models.git_platform import GitPlatform
from app.models.role import Role
from app.models.schema_registry import SchemaRegistry
from app.utils.class_loader import import_from_string


class Bundle(BaseModel):
    platforms: List[GitPlatform]  # We want classes, not instances
    datasources: List[DataSource]
    roles: List[Role]
    schema_registry: SchemaRegistry

    model_config = ConfigDict(
        extra="ignore",         # ignore unknown fields
        validate_default=True,
        # validate defaults
    )

    @field_validator("platforms", mode="before")
    @classmethod
    def resolve_platforms(cls, v: Any):
        out = []
        for item in v:
            if isinstance(item, dict):
                platform_name = item.get('name')
                platform_cls = import_from_string(f"app.models.git_platforms.{platform_name}")
                # platform_cls = import_from_string('git_platforms.github')
                out.append(platform_cls(**item))  # Append the class itself, not an instance
            elif isinstance(item, str):
                platform_cls = import_from_string(item)
                out.append(platform_cls)  # Append the class itself, not an instance
            else:
                out.append(item)  # Already a class object
        return out

    @field_validator("datasources", mode="before")
    @classmethod
    def resolve_datasources(cls, v: Any):
        out = []
        for item in v:
            if isinstance(item, dict):
                datasource_name = item.get('name')
                datasource_cls = import_from_string(f"app.models.datasources.{datasource_name}")
                ds_adapter_cls = import_from_string(f"app.models.datasources_adapters.{datasource_name}")

                # platform_cls = import_from_string('git_platforms.github')
                out.append(datasource_cls(**item))  # Append the class itself, not an instance
            elif isinstance(item, str):
                datasource_cls = import_from_string(item)
                out.append(datasource_cls)  # Append the class itself, not an instance
            else:
                out.append(item)  # Already a class object
        return out