from datetime import datetime
from typing import Dict, Any

from app.celery_app import celery as celery_app

# Models & Utils
from app.models.rule import Rule
from app.pipeline.sink import Sink
from app.pipeline.source import Source
from app.utils.normalized_pr import NormalizedPR
from app.utils.normalized_push import NormalizedPush
from app.utils.normalized_commit import NormalizedCommit, FileChange
from app.utils.enums.file_status import FileStatus

# Pipeline Components
from app.pipeline.transforms.parser import ContentParser
from app.pipeline.transforms.flattener import Flattenizer
from app.pipeline.transforms.differ import DiffExploder


def reconstruct_commit(commit_data: Dict[str, Any]) -> NormalizedCommit:
    """Helper to reconstruct NormalizedCommit from serialized dict."""
    # Reconstruct FileChange objects with Enums
    files = set()
    for f in commit_data.get('files', []):
        # Handle if f is dict (expected from JSON serialization)
        status_val = f.get('status')
        try:
            status_enum = FileStatus(status_val)
        except ValueError:
            # Fallback or default
            status_enum = FileStatus.MODIFIED

        files.add(FileChange(path=f.get('path'), status=status_enum))

    # Reconstruct Timestamp
    ts = commit_data.get('timestamp')
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            ts = None

    return NormalizedCommit(
        hash=commit_data.get('hash'),
        files=files,
        timestamp=ts
    )


@celery_app.task(name='app.data_manager', bind=True, queue='worker_agents')
def data_manager(self, platform_config: dict, datasource_config: dict, normalize_git_webhook: dict, rule_dict: dict):
    # 1. Reconstruct Event Object (NormalizedPush or NormalizedPR)
    git_event_type = normalize_git_webhook.pop('_type', None)
    commit_sha = None
    before_sha = None
    git_event = None
    branch= None

    # Fix nested commits list
    raw_commits = normalize_git_webhook.get('commits', [])
    commits = [reconstruct_commit(c) for c in raw_commits]
    normalize_git_webhook['commits'] = commits
    rule = Rule(**rule_dict)

    # fetch_previous_git = rule.resolve_sync_mode()

    if  rule.envAsPR == True and git_event_type == 'NormalizedPR':
        git_event = NormalizedPR(**normalize_git_webhook)
        before_sha = git_event.base_sha
        commit_sha = git_event.head_sha
        branch = git_event.head_branch
    else:
        git_event = NormalizedPush(**normalize_git_webhook)
        before_sha = git_event.before
        commit_sha = git_event.after
        branch = git_event.branch


    all_changed_files = git_event.get_all_changed_files()

    git_event.sort_commits(reverse=True)

    file_lifecycle = {}
    ignored_files = set()  # Optimization: Remember paths that failed matching

    for commit in git_event.commits:
        for file_change in commit.files:
            path = file_change.path

            # Optimization A: If we already know this file is irrelevant, skip it
            if path in ignored_files:
                continue

            # Optimization B: If we are already tracking this file, just update the earliest status
            if path in file_lifecycle:
                file_lifecycle[path]['earliest_status'] = file_change.status
                continue

            # First time encountering this file (Newest occurrence)
            # CHECK MATCH HERE (as requested)
            # branch = git_event.head_branch or git_event.branch
            match_context = rule.get_unique_key_and_env(file_path=path, branch=branch)

            if not match_context:
                # Mark as ignored so we don't check regex again for older commits
                ignored_files.add(path)
                continue

            # Match successful! Initialize lifecycle tracking
            file_lifecycle[path] = {
                'latest_status': file_change.status,
                'earliest_status': file_change.status,
                'match_context': match_context  # Store context to reuse later
            }

    files_to_process= []
    for file_path, lifecycle in file_lifecycle.items():
        current_hash = commit_sha
        previous_hash = before_sha

        if lifecycle['latest_status'] == FileStatus.REMOVED:
            current_hash = None

        if lifecycle['earliest_status'] == FileStatus.ADDED:
            previous_hash = None

        files_to_process.append({
            'file_path': file_path,
            'last_commit_hash': current_hash,
            'first_commit_hash': previous_hash,
            'match_context': lifecycle['match_context']
        })

    if not files_to_process:
        print(f"ℹ️ [Data Manager] No files matched the rule strategy for {git_event.repository}")
        return {'status': 'skipped', 'reason': 'no matching files'}

    if not files_to_process:
        return {'status': 'success', 'message': 'No matching files found'}

    source = Source.create(**platform_config)
    files_with_content = source.read(files_to_process, git_event.repository)

    parser = ContentParser()
    flattener = Flattenizer(root_key="varTrack")
    differ = DiffExploder()

    # Initialize Sink
    sink = Sink.create(**datasource_config)

    sink.connect()

    processed_files = 0
    total_rows_written = 0

    # Process Data Stream
    for file in files_with_content:
        try:
            # B. TRANSFORMS: Chain of Responsibility

            # 1. Parse (String -> Dict)
            curr_dict = parser.process(file['current'])
            prev_dict = parser.process(file['previous'])

            # 2. Flatten (Dict -> Flat Dict)
            curr_flat = flattener.process(curr_dict)
            prev_flat = flattener.process(prev_dict)

            rows = differ.process(
                current=curr_flat,
                previous=prev_flat,
                metadata=file['metadata']
            )

            # C. SINK: Write to Buffer
            for row in rows:
                sink.write(row)
                total_rows_written += 1

            processed_files += 1

        except Exception as e:
            print(f"⚠️ [Engine] Skipped file {file['file_path']}: {e}")

    # Final flush to database
    sink.flush()

    return {
        'status': 'success',
        'processed_files': processed_files,
        'total_rows': total_rows_written,
        'config_strategy': rule.fileName or "Map"
    }