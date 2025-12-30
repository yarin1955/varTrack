# app/business_logic/lifecycle.py
from typing import Dict, Any, Set, Union
from app.models.rule import Rule
from app.utils.normalized_pr import NormalizedPR
from app.utils.normalized_push import NormalizedPush


def get_file_lifecycle(
        git_event: Union[NormalizedPush, NormalizedPR],
        rule: Rule,
        branch: str
) -> Dict[str, Dict[str, Any]]:
    """
    Analyzes Git commits to track the lifecycle (earliest/latest status) of changed files
    and filters them based on matching rules.
    """
    # 1. Sort commits newest to oldest to correctly identify 'latest' vs 'earliest' state
    git_event.sort_commits(reverse=True)

    file_lifecycle = {}
    ignored_files = set()

    for commit in git_event.commits:
        for file_change in commit.files:
            path = file_change.path

            # Skip if we already determined this file doesn't match our rules
            if path in ignored_files:
                continue

            # If we've seen this file already (a newer version), update its earliest status
            if path in file_lifecycle:
                file_lifecycle[path]['earliest_status'] = file_change.status
                continue

            # First time seeing this file (this is its 'latest' state in this event)
            # Check if it matches the provided Rule patterns
            match_context = rule.get_unique_key_and_env(file_path=path, branch=branch)
            if not match_context:
                ignored_files.add(path)
                continue

            file_lifecycle[path] = {
                'latest_status': file_change.status,
                'earliest_status': file_change.status,
                'match_context': match_context
            }

    return file_lifecycle