from datetime import datetime
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
from app.utils.normalized_pr import NormalizedPR
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

    @staticmethod
    def is_push_event(event_type):
        return event_type == 'push'

    @staticmethod
    def is_pr_event(event_type):
        return event_type == 'pull_request'

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
        if "payload" in data and isinstance(data["payload"], dict):
            data = data["payload"]

        commits_data = data.get("commits", [])
        repo = data.get("repository", {}) or {}

        normalized_commits: List[NormalizedCommit] = []

        for commit in commits_data:
            # Parse timestamp if present
            ts_raw = commit.get("timestamp")  # e.g. "2024-01-01T12:34:56Z"
            ts: Optional[datetime] = None
            if ts_raw:
                # GitHub uses ISO 8601 + 'Z' for UTC (e.g. "...Z")
                # Replace trailing 'Z' with '+00:00' for datetime.fromisoformat
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))

            normalized_commit = NormalizedCommit(
                hash=commit.get("id", ""),
                added=commit.get("added", []) or [],
                modified=commit.get("modified", []) or [],
                removed=commit.get("removed", []) or [],
                timestamp=ts,
            )

            if file:
                # Only include commits that touch the given file
                if normalized_commit.has_file_changed(file) or normalized_commit.has_file_added(file):
                    normalized_commits.append(normalized_commit)
            else:
                normalized_commits.append(normalized_commit)


        return NormalizedPush(
            repository=repo.get("full_name", ""),
            branch=data.get("ref", ""),
            before=data.get("before", ""),
            after=data.get("after", ""),
            commits=normalized_commits,
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

    def normalize_pr_payload(self, payload: Dict[str, Any], newest_first: bool = False) -> "NormalizedPR":
        """
        Normalize PR payload and enrich with API data (files, real merge base).
        Requires API access because PR webhooks do not contain the full file list or merge base.
        """
        data = payload
        if "payload" in data and isinstance(data["payload"], dict):
            data = data["payload"]

        # Ensure we are authenticated to make API calls
        self.auth()

        # 1. Extract Core Info
        pr_data = data.get("pull_request", {}) or {}
        action = data.get("action", "")
        pr_number = data.get("number") or pr_data.get("number")

        # 2. Determine Repository
        repo_info = data.get("repository", {})
        if not repo_info:
            repo_info = pr_data.get("base", {}).get("repo", {})
        repository_full_name = repo_info.get("full_name", "")

        # 3. Extract Branches & Tips
        base = pr_data.get("base", {})
        head = pr_data.get("head", {})

        base_ref = base.get("ref", "")
        head_ref = head.get("ref", "")
        target_branch_sha = base.get("sha", "")
        head_sha = head.get("sha", "")
        is_approved = bool(data.get("is_approved", False))

        # 4. API CALL: Calculate Real Merge Base
        # The webhook 'base_sha' is often just the target tip, not the actual merge ancestor.
        base_sha = self.get_merge_base(repository_full_name, target_branch_sha, head_sha)
        if not base_sha:
            # Fallback if API fails, though diffs might be inaccurate
            base_sha = target_branch_sha

            # 5. API CALL: Fetch Changed Files
        # PR webhooks don't list all files. We must fetch them to populate the commit/file info.
        added_files = []
        modified_files = []
        removed_files = []

        try:
            gh_repo = self._github_client.get_repo(repository_full_name)
            pull_request = gh_repo.get_pull(int(pr_number))

            # get_files() is paginated and covers the entire PR diff
            for file in pull_request.get_files():
                if file.status == "added":
                    added_files.append(file.filename)
                elif file.status == "removed":
                    removed_files.append(file.filename)
                elif file.status == "modified":
                    modified_files.append(file.filename)
                elif file.status == "renamed":
                    # Treat rename as add + remove (or just add new name depending on logic)
                    added_files.append(file.filename)
                    if file.previous_filename:
                        removed_files.append(file.previous_filename)

        except Exception as e:
            print(f"Error fetching PR files: {e}")

        # 6. Create Synthetic Commit
        # Use PR updated_at as the timestamp for this event
        ts_raw = pr_data.get("updated_at") or pr_data.get("created_at")
        ts_synthetic: Optional[datetime] = None
        if ts_raw:
            try:
                # Handle GitHub's ISO format (e.g. 2023-01-01T12:00:00Z)
                ts_synthetic = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except ValueError:
                pass

        synthetic_commit = NormalizedCommit(
            hash=head_sha,
            added=added_files,
            modified=modified_files,
            removed=removed_files,
            timestamp=ts_synthetic
        )

        return NormalizedPR(
            id=str(pr_number),
            action=action,
            repository=repository_full_name,
            base_branch=base_ref,
            head_branch=head_ref,
            base_sha=base_sha,
            target_branch_sha=target_branch_sha,
            head_sha=head_sha,
            is_approved=is_approved,
            commits=[synthetic_commit]
        )

    # def normalize_pr_payload(self, payload: Dict[str, Any], newest_first: bool = False) -> "NormalizedPR":
    #     data = payload.get("payload", payload)
    #     self.auth()
    #
    #     pr = data.get("pull_request", {})
    #     base, head = pr.get("base", {}), pr.get("head", {})
    #     repo_name = (data.get("repository") or base.get("repo") or {}).get("full_name", "")
    #
    #     # OPTIMIZATION: Use a single API call ('compare') to get both the Real Merge Base and Changed Files.
    #     # This is significantly faster than calling get_merge_base() + get_pull().get_files() separately.
    #     try:
    #         repo = self._github_client.get_repo(repo_name)
    #         # compare() calculates the diff from the common ancestor (3-dot diff)
    #         diff = repo.compare(base.get("sha"), head.get("sha"))
    #
    #         base_sha = diff.merge_base_commit.sha
    #         files = diff.files
    #     except Exception as e:
    #         print(f"Warning: API compare failed ({e}). Falling back to payload data.")
    #         base_sha = base.get("sha", "")  # Fallback
    #         files = []
    #
    #     # Sort files into categories
    #     added, modified, removed = [], [], []
    #     for f in files:
    #         if f.status == "added":
    #             added.append(f.filename)
    #         elif f.status == "modified":
    #             modified.append(f.filename)
    #         elif f.status == "removed":
    #             removed.append(f.filename)
    #         elif f.status == "renamed":
    #             added.append(f.filename)
    #             if f.previous_filename: removed.append(f.previous_filename)
    #
    #     # Parse timestamp from payload (faster than parsing commit objects)
    #     ts = None
    #     if pr.get("updated_at"):
    #         try:
    #             ts = datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00"))
    #         except ValueError:
    #             pass
    #
    #     return NormalizedPR(
    #         id=str(data.get("number") or pr.get("number") or ""),
    #         action=data.get("action", ""),
    #         repository=repo_name,
    #         base_branch=base.get("ref", ""),
    #         head_branch=head.get("ref", ""),
    #         base_sha=base_sha,
    #         target_branch_sha=base.get("sha", ""),
    #         head_sha=head.get("sha", ""),
    #         is_approved=bool(data.get("is_approved", False)),
    #         commits=[NormalizedCommit(head.get("sha", ""), added, modified, removed, ts)]
    #     )

    def get_merge_base(self, repo_name: str, base_sha: str, head_sha: str) -> Optional[str]:
        """
        Calculates the merge base (common ancestor) between two commits using GitHub Compare API.
        """
        if not hasattr(self, '_github_client') or not self._github_client:
            self.auth()

        try:
            repo = self._github_client.get_repo(repo_name)
            # The 'compare' API with two SHAs automagically finds the merge base in the response
            comparison = repo.compare(base_sha, head_sha)
            if comparison.merge_base_commit:
                return comparison.merge_base_commit.sha
            return None
        except Exception as e:
            print(f"Error fetching merge base for {repo_name}: {e}")
            return None

    def get_pr_files(self, repo_name: str, pr_number: int) -> List[str]:
        """
        Fetches the list of files changed in a PR.
        """
        if not hasattr(self, '_github_client') or not self._github_client:
            self.auth()

        try:
            repo = self._github_client.get_repo(repo_name)
            pull = repo.get_pull(int(pr_number))
            # Paginated list, iterating yields all files
            return [f.filename for f in pull.get_files()]

        # for f in pull.get_files():
        #     status = f.status  # e.g. 'added', 'modified', 'removed', 'renamed'
        #     files_by_status.setdefault(status, []).append(f.filename)
        #
        # return files_by_status



        except Exception as e:
            print(f"Error fetching PR files for {repo_name}#{pr_number}: {e}")
            return []

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


    def generate_webhook_url(self, datasource: str= None) -> str:
        return super().generate_webhook_url(datasource)

    def git_clone(self, schemas_repo: SchemaRegistry) -> None:
        return super().git_clone(schemas_repo)

    async def get_file_from_commit(self, repo_name: str, commit_hash: str, file_path: str) -> Optional[str]:
        raw_url = f"https://github.com/{repo_name}/raw/{commit_hash}/{file_path}"
        response = requests.get(raw_url)
        return response.text

