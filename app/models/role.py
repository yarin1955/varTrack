from pydantic import BaseModel, ConfigDict
from typing import List, Union, Optional, Dict


class Role(BaseModel):
    platform: str
    datasource: Union[str, List[str]]
    fileName: Optional[str]
    repositories: List[str]
    excludeRepositories: List[str]
    envAsBranch: bool = False
    envAsPR: bool = False
    envAsTags: bool = False
    branchMap: Optional[Dict[str, str]] = None
    filePathMap: Optional[Dict[str, str]] = None
    uniqueKeyName: str = "{repoName}-{env}"
    variablesMap: Optional[Dict[str, str]] = None
    #prune: bool = False

    model_config = ConfigDict(
        extra="ignore",         # ignore unknown fields
        validate_default=True,  # validate defaults
    )
