from pydantic import BaseModel, ConfigDict
from typing import List

class SchemaRegistry(BaseModel):
    """
    Shared settings: endpoint + either a token or username/password.
    """
    platform: str
    repo: str
    branch: str

    model_config = ConfigDict(
        extra="ignore",         # ignore unknown fields
        validate_default=True,  # validate defaults
    )
