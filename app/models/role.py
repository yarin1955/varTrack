from pydantic import BaseModel, ConfigDict
from typing import List, Union


class Role(BaseModel):
    """
    Shared settings: endpoint + either a token or username/password.
    """
    platform: str
    datasource: Union[str, List[str]]
    fileName: str
    envAsBranch: bool
    prune: bool
    repositories: List[str]

    model_config = ConfigDict(
        extra="ignore",         # ignore unknown fields
        validate_default=True,  # validate defaults
    )
