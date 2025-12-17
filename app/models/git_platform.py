from abc import abstractmethod
from typing import Literal, Optional, List
from pydantic import BaseModel, ConfigDict, HttpUrl, Field

# Import your Factory Interface
from app.utils.interfaces.ifactory import IFactory

class GitPlatform(BaseModel, IFactory):
    """
    Base class for all Git Providers (GitHub, GitLab, etc.).
    It combines Pydantic data validation with the IFactory registration system.
    """

    # --- Identity ---
    # 'name' is required by the Factory to find the class,
    # and required by Pydantic to validate the instance.
    name: str
    endpoint: HttpUrl
    protocol: Literal["ssh", "http", "https"]

    # --- Credentials ---
    token: Optional[str] = Field(default=None)
    username: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None)
    secret: Optional[str] = Field(default=None)

    # --- Enterprise / Network ---
    verify_ssl: bool = Field(default=True)
    timeout: int = Field(default=30)
    max_retries: int = Field(default=3)

    # Pydantic Config: Ignore extra fields (like comments in JSON)
    model_config = ConfigDict(extra="ignore")

    # =========================================================
    # FACTORY IMPLEMENTATION
    # =========================================================

    @classmethod
    def load_module(cls, name: str):
        """
        Implementation of the IFactory lazy-loader.
        It tells the factory exactly where to look for plugins.
        """
        # 1. Import the package where your plugins live
        #    We do this inside the function to avoid circular import issues
        from app.models import git_platforms

        # 2. Use the helper from IFactory to load the specific file (e.g., 'github.py')
        cls._load_class_from_package_module(
            module_name=name,
            package_module=git_platforms  # Pass the module object
        )

    # =========================================================
    # ABSTRACT METHODS (Contract for Subclasses)
    # =========================================================

    @property
    @abstractmethod
    def event_type_header(self) -> str:
        """The HTTP header key used by the provider for event types (e.g. 'X-GitHub-Event')"""
        pass

    @property
    @abstractmethod
    def git_scm_signature(self) -> str:
        """The HTTP header key used for webhook signature verification"""
        pass

    @staticmethod
    @abstractmethod
    def is_push_event(event_type):
        pass

    @staticmethod
    @abstractmethod
    def is_pr_event(event_type):
        pass

    @abstractmethod
    def construct_clone_url(self, repo: str) -> str:
        """Generates the git clone URL (HTTPS or SSH) based on settings."""
        pass