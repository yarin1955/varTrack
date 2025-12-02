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

    # @staticmethod
    # async def get_file_from_commit(repo_path: str, commit_hash: str, file_path: str) -> Optional[str]:
    #     """
    #     Asynchronously get file content from a specific commit.
    #
    #     Args:
    #         repo_path: Path to the git repository
    #         commit_hash: Hash of the commit to read from
    #         file_path: Path to the file within the repository
    #
    #     Returns:
    #         File content as string, or None if file doesn't exist,
    #         or info string for binary files
    #
    #     Raises:
    #         git.exc.InvalidGitRepositoryError: If repo_path is not a valid git repo
    #         git.exc.BadName: If commit_hash is invalid
    #     """
    #
    #     def _get_file_sync():
    #         # Open the existing repository
    #         repo = git.Repo(repo_path)
    #         # Get commit object
    #         commit = repo.commit(commit_hash)
    #         try:
    #             # Access the file blob from the commit's tree
    #             blob = commit.tree[file_path]
    #             # Read the file content as text
    #             return blob.data_stream.read().decode('utf-8')
    #         except KeyError:
    #             # File doesn't exist in this commit
    #             return None
    #         except UnicodeDecodeError:
    #             # File is binary, return raw bytes info
    #             blob = commit.tree[file_path]
    #             return f"<Binary file, size: {blob.size} bytes>"
    #
    #     try:
    #         # Run the synchronous git operations in a thread pool
    #         loop = asyncio.get_event_loop()
    #         with ThreadPoolExecutor() as executor:
    #             result = await loop.run_in_executor(executor, _get_file_sync)
    #         return result
    #     except git.exc.InvalidGitRepositoryError:
    #         raise git.exc.InvalidGitRepositoryError(f"'{repo_path}' is not a valid Git repository")
    #     except git.exc.BadName as e:
    #         raise git.exc.BadName(f"Invalid commit hash: {e}")

    @abstractmethod
    async def get_file_from_commit(self, repo_name: str, commit_hash: str, file_path: str) -> Optional[str]:
        pass

        # repo_path= self.git_url_generator(repo_name)
        #
        # print(repo_path)
        #
        #
        # def _get_file_sync():
        #     """Synchronous helper function to be run in thread pool"""
        #     try:
        #         # Open the existing repository
        #         repo = git.Repo(repo_path)
        #
        #         # Get commit object
        #         commit = repo.commit(commit_hash)
        #
        #         try:
        #             # Access the file blob from the commit's tree
        #             blob = commit.tree[file_path]
        #             # Read the file content as text
        #             return blob.data_stream.read().decode('utf-8')
        #         except KeyError:
        #             # File doesn't exist in this commit
        #             return None
        #         except UnicodeDecodeError:
        #             # File is binary, return raw bytes info
        #             blob = commit.tree[file_path]
        #             return f"<Binary file, size: {blob.size} bytes>"
        #
        #     except git.exc.InvalidGitRepositoryError:
        #         raise git.exc.InvalidGitRepositoryError(f"'{repo_path}' is not a valid Git repository")
        #     except git.exc.BadName as e:
        #         raise git.exc.BadName(f"Invalid commit hash: {e}")
        #
        # # Run the synchronous Git operations in a thread pool to avoid blocking
        # loop = asyncio.get_event_loop()
        # return await loop.run_in_executor(None, _get_file_sync)

