from abc import ABC, abstractmethod
from typing import Optional, TypeVar
from pydantic import BaseModel, ConfigDict, HttpUrl

T = TypeVar('T')

class DataSource(BaseModel, ABC):
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

    # # @abstractmethod
    # def connect(self) -> T:...
    #
    # # @abstractmethod
    # def disconnect(self) -> T:...
    #
    # # @abstractmethod
    # def set(self) -> T:...
    #
    # def delete(self) -> T:...
    #
    # def create_adapter(self):
    #     pass


