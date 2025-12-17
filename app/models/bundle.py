from typing import List, Any
from pydantic import BaseModel, ConfigDict, field_validator

from app.models.datasource import DataSource
# Import your GitPlatform and other dependencies
from app.models.git_platform import GitPlatform

from typing import List, Any
from pydantic import BaseModel, ConfigDict, field_validator
# Import your GitPlatform and other dependencies
from app.models.git_platform import GitPlatform
from app.models.rule import Rule
from app.models.schema_registry import SchemaRegistry


class Bundle(BaseModel):
    platforms: List[GitPlatform]
    datasources: List[DataSource]
    rules: List[Rule]
    schema_registry: SchemaRegistry

    model_config = ConfigDict(
        extra="ignore",
        validate_default=True,
    )

    @field_validator("platforms", mode="before")
    @classmethod
    def resolve_platforms(cls, v: Any):
        out = []

        # Ensure input is iterable
        if not isinstance(v, list):
            return v

        for item in v:
            if isinstance(item, dict):
                # This calls GitPlatform.create(name="github", ...)
                # Because of the fix in IFactory, 'name' is passed to the Pydantic init.
                instance = GitPlatform.create(**item)
                out.append(instance)
            else:
                out.append(item)
        return out

    @field_validator("datasources", mode="before")
    @classmethod
    def resolve_datasources(cls, v: Any):
        out = []

        # Ensure input is iterable
        if not isinstance(v, list):
            return v

        for item in v:
            if isinstance(item, dict):
                # This calls GitPlatform.create(name="github", ...)
                # Because of the fix in IFactory, 'name' is passed to the Pydantic init.
                instance = DataSource.create(**item)
                out.append(instance)
            else:
                out.append(item)
        return out