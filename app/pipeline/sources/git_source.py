import gevent
from typing import List, Dict, Any
from app.pipeline.core import Source
from app.models.git_platform import GitPlatform


class GitSource(Source):
    def __init__(self, platform: GitPlatform, repo_name: str, files_to_process: List[Dict], before_sha: str = None):
        """
        Args:
            platform: Authenticated GitPlatform instance.
            repo_name: Name of the repository.
            files_to_process: List of dicts containing 'file_path', 'last_commit_hash', 'match_context'.
            before_sha: SHA of the previous commit (for diffing).
        """
        self.platform = platform
        self.repo = repo_name
        self.files = files_to_process
        self.before_sha = before_sha

    def read(self) -> List[Dict[str, Any]]:
        """
        Concurrent fetch of Current and Previous file contents using Gevent.
        Returns a list of dicts: {'current': str, 'previous': str, 'metadata': dict}
        """
        jobs = []

        # 1. Spawn greenlets for all fetch tasks (2 per file: current & previous)
        for item in self.files:
            # Task A: Get Current Content
            jobs.append(gevent.spawn(
                self.platform.get_file_from_commit,
                self.repo, item['last_commit_hash'], item['file_path']
            ))

            # Task B: Get Previous Content
            if self.before_sha:
                jobs.append(gevent.spawn(
                    self.platform.get_file_from_commit,
                    self.repo, self.before_sha, item['file_path']
                ))
            else:
                jobs.append(gevent.spawn(self._noop))

        # 2. Execute all network calls in parallel
        print(f"🚀 [GitSource] Fetching {len(jobs)} file versions concurrently...")
        gevent.joinall(jobs)

        # 3. Pair results back to files
        results = []
        # Get all results in order from the jobs list
        raw_results = [job.value for job in jobs]

        for i, item in enumerate(self.files):
            curr_content = raw_results[i * 2]
            prev_content = raw_results[(i * 2) + 1]

            results.append({
                "current": curr_content,
                "previous": prev_content,
                "metadata": item['match_context'],  # Contains 'env', 'key', etc.
                "file_path": item['file_path']
            })

        return results

    def _noop(self):
        return None