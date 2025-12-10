from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, TypeVar, List, Literal, Dict, Any
from pydantic import BaseModel, ConfigDict, HttpUrl
import git
import asyncio
from app.models.schema_registry import SchemaRegistry

T = TypeVar('T')

class GitPlatform(BaseModel, ABC):
    """
    Shared settings: endpoint + either a token or username/password.
    """
    name: str
    endpoint: HttpUrl
    token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    secret: Optional[str] = None
    protocol: Literal["ssh", "http", "https"]
    events: Optional[List[str]] = ["push"]

    model_config = ConfigDict(
        extra="ignore",         # ignore unknown fields
        validate_default=True,  # validate defaults
    )

    @property
    @abstractmethod
    def event_type_header(self):
        pass

    @property
    @abstractmethod
    def git_scm_signature(self):
        pass

    @abstractmethod
    def auth(self) -> T:
        pass

    @abstractmethod
    def closed(self) -> T:
        pass

    @abstractmethod
    def create_webhooks(self, repositories: List[str] | str, datasource: str=None):
        pass

    @abstractmethod
    def resolve_repositories(self, patterns: List[str], exclude_patterns: Optional[List[str]] = None) -> List[str]:
        """Convert wildcard patterns (e.g. 'org/*') into actual repo names."""
        pass

    @staticmethod
    @abstractmethod
    def is_push_event(event_type):
        pass

    @staticmethod
    @abstractmethod
    def is_pr_event(event_type):
        pass

    @staticmethod
    @abstractmethod
    def normalize_push_payload(payload: Dict[str, Any], file: Optional[str] = None):
        pass

    @abstractmethod
    def generate_webhook_url(self, datasource: str= None) -> str:
        if datasource:
            return f"https://smee.io/wbkMDPCrORy5Hr/webhooks/{self.name}/{datasource}"
        return f"https://smee.io/wbkMDPCrORy5Hr/webhooks/schemas"

    async def git_clone(self, schema: SchemaRegistry):

        folder_path = Path("./schemas")
        folder_path.mkdir(exist_ok=True)
        try:
            clone_path= f"./schemas/{schema.repo}"

            repo_url = self.git_url_generator(schema.repo)

            git.Repo.clone_from(
                repo_url,
                clone_path,
                branch=schema.branch,
                depth=1  # Shallow clone for faster operation
            )

        except git.exc.GitCommandError as e:
            print(f"Git error: {e}")
        except Exception as e:
            print(f"Error: {e}")

        return self

    def git_url_generator(self, repo: str) -> str:
        clean_endpoint = str(self.endpoint).split('//', 1)[1]
        print(f"{self.protocol}://{clean_endpoint}{self.username}/{repo}.git")
        return f"{self.protocol}://{clean_endpoint}{self.username}/{repo}.git"

    def setup_webhooks(self, schema: SchemaRegistry, repos: List[str], datasource, exclude_repos: List[str] = None):
        builder: GitPlatform = self.auth()
        if schema.platform == self.name:
            asyncio.run(builder.git_clone(schema))
            builder = builder.create_webhooks(schema.repo)
        if repos:
            print(f"Creating webhooks for {len(repos)} repositories: {repos}")
            builder = builder.create_webhooks(repos, datasource)
        else:
            print("No repositories found for webhook creation")

        return builder.closed()

    @abstractmethod
    def get_file_from_commit(self, repo_name: str, commit_hash: str, file_path: str) -> Optional[str]:
        pass