import asyncio
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

    async def read(self) -> List[Dict[str, Any]]:
        """
        Concurrent fetch of Current and Previous file contents.
        Returns a list of dicts: {'current': str, 'previous': str, 'metadata': dict}
        """
        tasks = []

        # 1. Create all fetch tasks (2 per file: current & previous)
        for item in self.files:
            # Task A: Get Current Content
            tasks.append(self.platform.get_file_from_commit(
                self.repo, item['last_commit_hash'], item['file_path']
            ))

            # Task B: Get Previous Content
            if self.before_sha:
                tasks.append(self.platform.get_file_from_commit(
                    self.repo, self.before_sha, item['file_path']
                ))
            else:
                tasks.append(self._noop())

        # 2. Execute all network calls in parallel
        print(f"🚀 [GitSource] Fetching {len(tasks)} file versions concurrently...")
        raw_results = await asyncio.gather(*tasks)

        # 3. Pair results back to files
        results = []
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

    async def _noop(self):
        return None