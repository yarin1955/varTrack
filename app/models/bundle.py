from typing import List, Any
from pydantic import BaseModel, ConfigDict, field_validator

from app.models.datasource import DataSource
from app.models.git_platform import GitPlatform
from app.models.role import Role
from app.models.schema_registry import SchemaRegistry

from app.utils.factories.datasource_factory import DataSourceFactory
from app.utils.factories.platform_factory import PlatformFactory

class Bundle(BaseModel):
    platforms: List[GitPlatform]
    datasources: List[DataSource]
    roles: List[Role]
    schema_registry: SchemaRegistry

    model_config = ConfigDict(
        extra="ignore",
        validate_default=True,
    )

    @field_validator("platforms", mode="before")
    @classmethod
    def resolve_platforms(cls, v: Any):
        out = []
        for item in v:
            if isinstance(item, dict):
                instance = PlatformFactory.create(**item)
                out.append(instance)
            else:
                out.append(item)
        return out

    @field_validator("datasources", mode="before")
    @classmethod
    def resolve_datasources(cls, v: Any):
        out = []
        for item in v:
            if isinstance(item, dict):
                instance = DataSourceFactory.create(**item)
                out.append(instance)
            else:                out.append(item)
        return out