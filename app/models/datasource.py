from abc import ABC, abstractmethod
from typing import Optional, TypeVar
from pydantic import BaseModel, ConfigDict, HttpUrl

from app.utils.interfaces.ifactory import IFactory

T = TypeVar('T')

class DataSource(BaseModel, IFactory):
    """
    Shared settings: endpoint + either a token or username/password.
    """
    name: str
    endpoint: HttpUrl
    token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    model_config = ConfigDict(
        extra="ignore",         # ignore unknown fields
        validate_default=True,  # validate defaults
    )

    @classmethod
    def load_module(cls, name: str):
        from app.models import datasources
        cls._load_class_from_package_module(
            module_name=name,
            package_module=datasources
        )


