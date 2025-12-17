from typing import Optional
from pydantic import ConfigDict, Field
from app.models.git_platform import GitPlatform

class GitHubSettings(GitPlatform):
    """
    Strict Configuration Model for GitHub.

    Attributes:
        org_name: Optional organization to scope operations (aliased as 'orgName' for JSON).
        verify_ssl: Disable for self-signed Enterprise certificates.
        timeout: API request timeout (seconds).
        max_retries: Retry count for flaky connections.
        page_size: Pagination limit (max 100 for GitHub).
    """

    # --- Organization Scope ---
    org_name: Optional[str] = Field(
        default=None,
        alias="orgName",
        description="Target GitHub Organization. If set, operations are scoped to this org."
    )

    # --- Connection Reliability (Enterprise / Self-Hosted) ---
    verify_ssl: bool = Field(
        default=True,
        description="Verify SSL certificates. Set to False for self-signed Enterprise certs."
    )

    timeout: int = Field(
        default=30,
        ge=1,
        description="API request timeout in seconds."
    )

    max_retries: int = Field(
        default=3,
        ge=0,
        description="Number of retries for failed API requests."
    )

    page_size: int = Field(
        default=100,
        ge=1,
        le=100,
        description="Number of items to fetch per page (GitHub API limit is 100)."
    )

    # --- Pydantic Configuration ---
    model_config = ConfigDict(
        extra="forbid",  # Prevent typos in config
        validate_default=True,
        populate_by_name=True  # Allows using "orgName" in JSON to populate "org_name"
    )

    # --- Properties & Constants ---

    @property
    def event_type_header(self) -> str:
        return 'X-Github-Event'

    @property
    def git_scm_signature(self) -> str:
        return 'X-Hub-Signature-256'

    @property
    def base_api_url(self) -> str:

        url = str(self.endpoint).rstrip('/')

        # Case A: Public GitHub
        if "github.com" in url and "api.github.com" not in url:
            return "https://api.github.com"

        # Case B: Already an API URL (has /api/v3 or is api.github.com)
        if "api/v3" in url or "api.github.com" in url:
            return url

        # Case C: Enterprise Fallback (Append standard suffix)
        return f"{url}/api/v3"

    @staticmethod
    def is_push_event(event_type):
        return event_type == 'push'

    @staticmethod
    def is_pr_event(event_type):
        return event_type == 'pull_request'

    def construct_clone_url(self, repo: str) -> str:
        """
        Generates a secure clone URL.
        - Handles 'owner/repo' vs 'repo' inputs.
        - Injects Personal Access Token into HTTPS URLs for auth.
        - Handles SSH formatting.
        """

        # 1. Normalize Repo Name (Ensure 'owner/repo' format)
        if "/" not in repo:
            # Fallback to org_name or username if only repo name is provided
            owner = self.org_name or self.username
            full_repo_name = f"{owner}/{repo}"
        else:
            full_repo_name = repo

        # 2. Handle SSH
        if self.protocol == "ssh":
            # Pydantic v2 uses .host, v1 uses .host
            domain = self.endpoint.host if hasattr(self.endpoint, 'host') else self.endpoint.split('//')[-1].split('/')[
                0]
            return f"git@{domain}:{full_repo_name}.git"

        # 3. Handle HTTPS (Inject Auth)
        # Convert HttpUrl to string and strip trailing slash
        base_url = str(self.endpoint).rstrip("/")

        # Remove the 'https://' scheme for easier reconstruction
        if "://" in base_url:
            scheme, clean_domain = base_url.split("://", 1)
        else:
            scheme, clean_domain = "https", base_url

        if self.token:
            # GitHub pattern: https://oauth2:TOKEN@github.com/owner/repo.git
            # (You can also use just the token as the user, but oauth2 is explicit)
            return f"{scheme}://{self.token}@{clean_domain}/{full_repo_name}.git"

        if self.username and self.password:
            # Basic Auth: https://user:pass@github.com...
            return f"{scheme}://{self.username}:{self.password}@{clean_domain}/{full_repo_name}.git"

        # Public / No Auth
        return f"{scheme}://{clean_domain}/{full_repo_name}.git"
