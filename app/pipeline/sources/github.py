import base64
import fnmatch
from datetime import datetime
from typing import Optional, Dict, List, Any

from github import Github, GithubException, Auth

from app.models.git_platforms.github import GitHubSettings
from app.utils.interfaces.isource import ISource
from app.utils.normalized_commit import NormalizedCommit
from app.utils.normalized_pr import NormalizedPR
from app.utils.normalized_push import NormalizedPush


class GitHubSource(ISource):
    """
    Operational Logic for GitHub.
    Handles authentication, API interactions, and payload normalization.
    """

    def __init__(self, settings: GitHubSettings):
        self.settings = settings
        self.client: Github = None

    # --- Connection Management ---

    def auth(self) -> "GitHubSource":
        """Authenticates and initializes the PyGithub client."""
        # Determine Auth Method
        if self.settings.token:
            auth = Auth.Token(self.settings.token)
        else:
            auth = Auth.Login(self.settings.username, self.settings.password)

        # Initialize Client with Settings
        self.client = Github(
            auth=auth,
            base_url=self.settings.base_api_url,
            verify=self.settings.verify_ssl,
            timeout=self.settings.timeout,
            retry=self.settings.max_retries,
            per_page=self.settings.page_size
        )

        # Verify Connection (Lazy Check)
        try:
            # This forces a request to check if credentials are valid
            self.client.get_user().login
        except Exception as e:
            self.client = None
            raise ConnectionError(f"GitHub authentication failed: {e}")

        return self

    def closed(self) -> "GitHubSource":
        """Closes the active connection."""
        if self.client:
            self.client.close()
            self.client = None
        return self

    def _ensure_connected(self):
        """Helper to ensure we have an active client."""
        if not self.client:
            self.auth()

    # --- Repository Management ---

    def resolve_repositories(self, patterns: List[str], exclude_patterns: Optional[List[str]] = None) -> List[str]:
        """
        Resolves a list of repository patterns (including wildcards) to a list of repository names.
        Respects the 'org_name' setting for scoping.
        """
        self._ensure_connected()
        resolved_repos = set()

        # 1. Determine Scope (User or Org)
        if self.settings.org_name:
            target = self.client.get_organization(self.settings.org_name)
        else:
            target = self.client.get_user()

        # 2. Check for Wildcards
        has_wildcard = any('*' in p or '?' in p for p in patterns)

        if has_wildcard:
            # Fetch ALL repos to perform pattern matching (slower but necessary for wildcards)
            all_repos = [repo.name for repo in target.get_repos()]
            for pattern in patterns:
                clean_pattern = pattern.split('/')[-1]  # Remove owner prefix if present for matching
                matches = fnmatch.filter(all_repos, clean_pattern)
                resolved_repos.update(matches)
        else:
            # Direct Fetch (faster)
            for pattern in patterns:
                repo_name = pattern.split('/')[-1]
                try:
                    target.get_repo(repo_name)
                    resolved_repos.add(repo_name)
                except Exception as e:
                    print(f"Warning: Repository '{repo_name}' not found: {e}")

        # 3. Apply Exclusion Patterns
        if exclude_patterns:
            final_list = []
            for repo in resolved_repos:
                is_excluded = False
                for ex_pattern in exclude_patterns:
                    clean_ex = ex_pattern.split('/')[-1]
                    if fnmatch.fnmatch(repo, clean_ex):
                        is_excluded = True
                        break
                if not is_excluded:
                    final_list.append(repo)
            return final_list

        return list(resolved_repos)

    def create_webhooks(self, repositories: List[str] | str, datasource: str = None):
        """
        Ensures webhooks exist on the specified repositories.
        """
        self._ensure_connected()
        repos_list = [repositories] if isinstance(repositories, str) else repositories

        for repo_name in repos_list:
            # Construct full name if needed
            if '/' not in repo_name:
                if self.settings.org_name:
                    full_repo_name = f"{self.settings.org_name}/{repo_name}"
                else:
                    full_repo_name = f"{self.settings.username}/{repo_name}"
            else:
                full_repo_name = repo_name

            try:
                repo = self.client.get_repo(full_repo_name)

                url = self.settings.construct_clone_url(repo_name)
                config = {
                    "url": url,
                    "content_type": "json",
                    "insecure_ssl": "0"
                }

                # Check for existing hook to update instead of create
                existing = None
                for hook in repo.get_hooks():
                    if (hook.config or {}).get("url") == url:
                        existing = hook
                        break

                if existing:
                    existing.edit(name="web", config=config, active=True)
                    print(f"[GitHub] Updated webhook for {full_repo_name}")
                else:
                    repo.create_hook(name="web", config=config, active=True)
                    print(f"[GitHub] Created webhook for {full_repo_name}")

            except GithubException as e:
                print(f"[GitHub Error] Failed to configure webhook for {full_repo_name}: {e}")

    # --- File Operations ---

    def get_file_from_commit(self, repo_name: str, commit_hash: str, file_path: str) -> Optional[str]:
        """
        Fetches file content. Handles standard files and large blobs (>1MB).
        """
        self._ensure_connected()
        try:
            repo = self.client.get_repo(repo_name)

            # Attempt 1: Standard Content API (Fast, limit 1MB)
            try:
                content = repo.get_contents(file_path, ref=commit_hash)
                if isinstance(content, list):
                    return None  # Directory
                return content.decoded_content.decode('utf-8')
            except GithubException as e:
                # 403 usually indicates the file is too large for this endpoint
                if e.status != 403:
                    raise e

                # Attempt 2: Git Data API (Tree -> Blob, limit 100MB)
                print(f"[GitHub] File {file_path} >1MB. Using Blob API.")
                tree = repo.get_git_tree(commit_hash, recursive=True)

                blob_sha = None
                for element in tree.tree:
                    if element.path == file_path:
                        blob_sha = element.sha
                        break

                if not blob_sha:
                    return None

                blob = repo.get_git_blob(blob_sha)
                if blob.encoding == 'base64':
                    return base64.b64decode(blob.content).decode('utf-8')
                return blob.content.decode('utf-8')

        except Exception as e:
            print(f"[GitHub Error] fetching '{file_path}': {e}")
            return None

    # --- Payload Normalization ---

    def normalize_pr_payload(self, payload: Dict[str, Any], newest_first: bool = False) -> NormalizedPR:
        """
        Parses a PR webhook payload and fetches missing details (files, real merge base) via API.
        """
        self._ensure_connected()

        data = payload.get("payload", payload) if "payload" in payload else payload

        # 1. Extract Basic Info
        pr_data = data.get("pull_request", {}) or {}
        # Fallback to finding repo info in 'base' if not at root
        repo_info = data.get("repository", {}) or pr_data.get("base", {}).get("repo", {})
        repo_full_name = repo_info.get("full_name", "")
        pr_number = data.get("number") or pr_data.get("number")

        # 2. Extract Git Refs
        base_sha_ref = pr_data.get("base", {}).get("sha")
        head_sha = pr_data.get("head", {}).get("sha")

        # 3. API Call: Get Real Merge Base (Triple Dot Diff)
        # We need the common ancestor, not just the target branch tip
        real_base_sha = self._get_merge_base(repo_full_name, base_sha_ref, head_sha)

        # 4. API Call: Get Changed Files
        added, modified, removed = self._get_pr_file_changes(repo_full_name, pr_number)

        # 5. Build Synthetic Commit Object
        ts_raw = pr_data.get("updated_at") or pr_data.get("created_at")
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if ts_raw else None

        commit = NormalizedCommit(
            hash=head_sha,
            added=added,
            modified=modified,
            removed=removed,
            timestamp=ts
        )

        return NormalizedPR(
            id=str(pr_number),
            action=data.get("action", ""),
            repository=repo_full_name,
            base_branch=pr_data.get("base", {}).get("ref", ""),
            head_branch=pr_data.get("head", {}).get("ref", ""),
            base_sha=real_base_sha or base_sha_ref,
            target_branch_sha=base_sha_ref,
            head_sha=head_sha,
            is_approved=data.get("is_approved", False),  # Custom field or generic
            commits=[commit]
        )

    @staticmethod
    def normalize_push_payload(payload: Dict[str, Any], file: Optional[str] = None) -> NormalizedPush:
        """
        Parses a Push webhook payload. Pure logic, no API calls required.
        """
        data = payload.get("payload", payload) if "payload" in payload else payload
        repo = data.get("repository", {}) or {}

        commits = []
        for c in data.get("commits", []):
            ts_raw = c.get("timestamp")
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if ts_raw else None

            nc = NormalizedCommit(
                hash=c.get("id", ""),
                added=c.get("added", []) or [],
                modified=c.get("modified", []) or [],
                removed=c.get("removed", []) or [],
                timestamp=ts
            )

            # Filter by file if requested
            if not file or nc.has_file_changed(file) or nc.has_file_added(file):
                commits.append(nc)

        return NormalizedPush(
            repository=repo.get("full_name", ""),
            branch=data.get("ref", ""),
            before=data.get("before", ""),
            after=data.get("after", ""),
            commits=commits
        )

    # --- Internal Helpers ---

    def _get_merge_base(self, repo_name: str, base_sha: str, head_sha: str) -> Optional[str]:
        try:
            repo = self.client.get_repo(repo_name)
            comparison = repo.compare(base_sha, head_sha)
            if comparison.merge_base_commit:
                return comparison.merge_base_commit.sha
        except Exception:
            # Fallback to provided base if comparison fails
            return None
        return None

    def _get_pr_file_changes(self, repo_name: str, pr_number: int):
        added, modified, removed = [], [], []
        try:
            repo = self.client.get_repo(repo_name)
            pull = repo.get_pull(int(pr_number))

            for f in pull.get_files():
                if f.status == "added":
                    added.append(f.filename)
                elif f.status == "removed":
                    removed.append(f.filename)
                elif f.status == "modified":
                    modified.append(f.filename)
                elif f.status == "renamed":
                    added.append(f.filename)
                    if f.previous_filename:
                        removed.append(f.previous_filename)
        except Exception as e:
            print(f"[GitHub Error] fetching PR files: {e}")

        return added, modified, removed