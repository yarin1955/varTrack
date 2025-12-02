from typing import Optional, Dict, List, Any
import requests
from github import Github, GithubException
from github import Auth
from pydantic import ConfigDict
import fnmatch
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
    def event_type_header(self) -> str:
        return 'X-Github-Event'

    @property
    def git_scm_signature(self) -> str:
        return 'X-Hub-Signature-256'

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
    def normalize_push_payload(payload: Dict[str, Any], file: Optional[str] = None) -> NormalizedPush:
        # Check if we need to access 'payload' key (if passed as wrapper) or use directly
        # Adjusting to handle standard GitHub webhook JSON payload
        data = payload
        if 'payload' in data and isinstance(data['payload'], dict):
            data = data['payload']

        commits_data = data.get("commits", [])
        repo = data.get('repository', {})

        normalized_commits = []
        for commit in commits_data:
            normalized_commit = NormalizedCommit(
                hash=commit.get('id', ''),
                added=commit.get('added', []),
                modified=commit.get('modified', []),
                removed=commit.get('removed', [])
            )

            # If file filter is provided, only include commits that touch that file
            if file:
                if normalized_commit.has_file_changed(file) or normalized_commit.has_file_added(file):
                    normalized_commits.append(normalized_commit)
            else:
                # If no file filter, include all commits
                normalized_commits.append(normalized_commit)

        return NormalizedPush(
            provider='github',
            repository=repo.get('full_name', ''),
            ref=data.get('ref', ''),
            before=data.get('before'),
            after=data.get('after'),
            commits=normalized_commits
        )

    def closed(self):
        """Close the GitHub connection and clear cached client"""
        if self._github_client:
            self._github_client.close()
            self._github_client = None

        return self

    def resolve_repositories(self, patterns: List[str], exclude_patterns: Optional[List[str]] = None) -> List[str]:
        """
        Resolves final repository list by applying inclusion patterns AND exclusion patterns.
        """
        if not self._github_client:
            self.auth()

        resolved_repos = set()

        # 1. Determine Scope
        if self.orgName:
            target = self._github_client.get_organization(self.orgName)
        else:
            target = self._github_client.get_user()

        # 2. Check if we need a full fetch (Wildcards present?)
        has_wildcard = any('*' in p or '?' in p for p in patterns)

        if has_wildcard:
            # Slow Path: Fetch ALL repos to match wildcards
            all_repos = [repo.name for repo in target.get_repos()]

            for pattern in patterns:
                # Match against just the repo name (ignoring owner prefix for now)
                clean_pattern = pattern.split('/')[-1]
                matches = fnmatch.filter(all_repos, clean_pattern)
                resolved_repos.update(matches)
        else:
            # Fast Path: Verify specific repos exist
            for pattern in patterns:
                repo_name = pattern.split('/')[-1]
                try:
                    # Just check if it exists (API HEAD call)
                    target.get_repo(repo_name)
                    resolved_repos.add(repo_name)
                except Exception as e:
                    print(f"Warning: Repository '{repo_name}' not found: {e}")

        # 3. Apply Exclusions
        if exclude_patterns:
            final_list = []
            for repo in resolved_repos:
                is_excluded = False
                for ex_pattern in exclude_patterns:
                    # Match against "repo" OR "owner/repo" logic if needed
                    # Standardizing on simple name match for simplicity
                    clean_ex = ex_pattern.split('/')[-1]

                    if fnmatch.fnmatch(repo, clean_ex):
                        is_excluded = True
                        break

                if not is_excluded:
                    final_list.append(repo)
            return final_list

        return list(resolved_repos)

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
        raw_url = f"https://github.com/{repo_name}/raw/{commit_hash}/{file_path}"
        response = requests.get(raw_url)
        return response.text

