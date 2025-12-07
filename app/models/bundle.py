from typing import List, Any
from pydantic import BaseModel, ConfigDict, field_validator

from app.models.datasource import DataSource
from app.models.ds_adapter import DataSourceAdapter
from app.models.git_platform import GitPlatform
from app.models.role import Role
from app.models.schema_registry import SchemaRegistry
# from app.utils.class_loader import safe_load_plugin
from app.models.datasources import load_module as ds_loader
from app.models.datasources_adapters import load_module as ds_adapter_loader
from app.models.git_platforms import load_module as platform_loader

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
                platform_cls = platform_loader(f"{platform_name}", GitPlatform)
                # platform_cls = import_from_string('git_platforms.github')
                out.append(platform_cls(**item))  # Append the class itself, not an instance
            elif isinstance(item, str):
                platform_cls = platform_loader(item)
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
                datasource_cls = ds_loader(f"{datasource_name}", DataSource)
                ds_adapter_cls = ds_adapter_loader(f"{datasource_name}", DataSourceAdapter)

                # platform_cls = import_from_string('git_platforms.github')
                out.append(datasource_cls(**item))  # Append the class itself, not an instance
            elif isinstance(item, str):
                datasource_cls = ds_loader(item)
                out.append(datasource_cls)  # Append the class itself, not an instance
            else:
                out.append(item)  # Already a class object
        return out