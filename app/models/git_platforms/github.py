from typing import Optional, Dict
import requests
from github import Github, GithubException
from github import Auth
from pydantic import ConfigDict

from app.models.git_platform import GitPlatform
from app.models.schema_registry import SchemaRegistry
from app.utils.factories.platform_factory import PlatformFactory
from app.utils.normalized_commit import NormalizedCommit
from app.utils.normalized_push import NormalizedPush


@PlatformFactory.register()
class GitHubSettings(GitPlatform):
    hostname: Optional[str] = None
    # events: List[str]
    orgName: Optional[str] = None
    _github_client: Github

    # event_type_header: str = Field(default="X-GitHub-Event", exclude=True)
    # git_scm_signature: str = Field(default="X-Hub-Signature-256", exclude=True)

    model_config = ConfigDict(
        extra="forbid",  # ignore unknown fields
        validate_default=True,  # validate defaults
    )

    @property
    def event_type_header(self):
        return "X-GitHub-Event"

    @property
    def git_scm_signature(self):
        return "X-Hub-Signature-256"

    # @property
    # def event_type_header(self):
    #     return self._event_type_header

    def auth(self):
        # Return cached client if already authenticated
        # if self._github_client is not None:
        #     return self._github_client
        # Create new authentication
        if self.token:
            auth = Auth.Token(self.token)
        else:
            auth = Auth.Login(self.username, self.password)

        self._github_client = Github(auth=auth)

        # Verify authentication works
        try:
            self._github_client.get_user().login
        except Exception as e:
            self._github_client = None  # Reset on auth failure
            raise e

        return self

    @staticmethod
    def normalize_push_payload(payload, file) -> NormalizedPush:
        payload= payload.json.get('payload')
        commits_data = payload.get("commits", [])
        repo = payload.get('repository', {})

        normalized_commits = []
        for commit in commits_data:
            normalized_commit = NormalizedCommit(
                hash=commit.get('id', ''),
                added=commit.get('added', []),
                modified=commit.get('modified', []),
                removed=commit.get('removed', [])
            )

            if normalized_commit.has_file_changed(file) or normalized_commit.has_file_added(file):
                normalized_commits.append(normalized_commit)

        return NormalizedPush(
            provider='github',
            repository=repo.get('full_name', ''),
            ref=payload.get('ref', ''),
            before=payload.get('before'),
            after=payload.get('after'),
            commits=normalized_commits
        )

    def closed(self):
        """Close the GitHub connection and clear cached client"""
        if self._github_client:
            self._github_client.close()
            self._github_client = None

        return self

    def create_webhooks(self, repositories, datasource=None):

        if isinstance(repositories, str):
            repositories = [repositories]

        for repo_name in repositories:
            # Get repository object
            repo = self._github_client.get_repo(f"{self.username}/{repo_name}")

            url: str = self.generate_webhook_url(datasource)

            # Prepare webhook configuration
            config = {
                "url": url,
                "content_type": "json",
                "insecure_ssl": "0"
            }

            try:
                existing = None
                for hook in repo.get_hooks():
                    if (hook.config or {}).get("url") == url:
                        existing = hook
                        break

                if existing:
                    existing.edit(name="web", config=config, events=self.events, active=True)
                    hook = existing
                    print(f"[webhook] updated existing webhook id={hook.id}")
                else:
                    hook = repo.create_hook(name="web", config=config, events=self.events, active=True)
                    print(f"[webhook] created webhook id={hook.id}")

            except GithubException as e:
                raise SystemExit(f"[webhook error] {e.data if hasattr(e, 'data') else e}")

        return self

                # Add secret if provided
                # if webhook_secret:
                #     config["secret"] = webhook_secret

                # Create the webhook
        #         repo.create_hook(
        #             name="web",
        #             config=config,
        #             events=self.events,
        #             active=True
        #         )
        #

    def generate_webhook_url(self, datasource: str= None) -> str:
        return super().generate_webhook_url(datasource)

    def git_clone(self, schemas_repo: SchemaRegistry) -> None:
        return super().git_clone(schemas_repo)

    async def get_file_from_commit(self, repo_name: str, commit_hash: str, file_path: str) -> Optional[str]:
        raw_url = f"https://github.com/{self.username}/{repo_name}/raw/{commit_hash}/{file_path}"
        response = requests.get(raw_url)
        return response.text

