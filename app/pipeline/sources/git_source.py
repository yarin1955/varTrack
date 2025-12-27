from typing import List, Dict, Any
from app.models.git_platform import GitPlatform
from app.pipeline.source import Source
from concurrent.futures import ThreadPoolExecutor

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
        Concurrent fetch using Standard Threads.
        Debugger Safe. Windows Safe.
        """
        results = []

        # Fixed pool of 20 threads for file fetching
        with ThreadPoolExecutor(max_workers=20) as executor:
            print(f"🚀 [GitSource] Fetching file versions with 20 threads...")

            future_tasks = []

            for item in self.files:
                # Task A: Get Current Content
                future_curr = executor.submit(
                    self.platform.get_file_from_commit,
                    self.repo, item['last_commit_hash'], item['file_path']
                )

                # Task B: Get Previous Content (or None)
                future_prev = None
                if self.before_sha:
                    future_prev = executor.submit(
                        self.platform.get_file_from_commit,
                        self.repo, self.before_sha, item['file_path']
                    )

                # Store futures to retrieve later
                future_tasks.append({
                    "future_curr": future_curr,
                    "future_prev": future_prev,
                    "metadata": item['match_context'],
                    "file_path": item['file_path']
                })

            # Collect results (blocks until threads finish)
            for task in future_tasks:
                curr_content = task["future_curr"].result()
                prev_content = task["future_prev"].result() if task["future_prev"] else None

                results.append({
                    "current": curr_content,
                    "previous": prev_content,
                    "metadata": task["metadata"],
                    "file_path": task["file_path"]
                })

        return results

    def _noop(self):
        return None