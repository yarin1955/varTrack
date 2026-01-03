from datetime import datetime
from typing import Dict, Any

from app.business_logic.lifecycle import get_file_lifecycle
from app.celery_app import celery as celery_app

# Models & Utils
from app.models.rule import Rule
from app.pipeline.source import Source
from app.pipeline.sink import Sink
from app.utils.normalized_pr import NormalizedPR
from app.utils.normalized_push import NormalizedPush
from app.utils.normalized_commit import NormalizedCommit, FileChange
from app.utils.enums.file_status import FileStatus
from app.business_logic.sync_engine import calculate_sync_rows
# Pipeline Components
from app.pipeline.transforms.parser import ContentParser
from app.pipeline.transforms.flattener import Flattenizer



def reconstruct_commit(commit_data: Dict[str, Any]) -> NormalizedCommit:
    """Helper to reconstruct NormalizedCommit from serialized dict."""
    files = set()
    for f in commit_data.get('files', []):
        status_val = f.get('status')
        try:
            status_enum = FileStatus(status_val)
        except ValueError:
            status_enum = FileStatus.MODIFIED

        files.add(FileChange(path=f.get('path'), status=status_enum))

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
    branch = None

    raw_commits = normalize_git_webhook.get('commits', [])
    commits = [reconstruct_commit(c) for c in raw_commits]
    normalize_git_webhook['commits'] = commits
    rule = Rule(**rule_dict)

    if rule.envAsPR == True and git_event_type == 'NormalizedPR':
        git_event = NormalizedPR(**normalize_git_webhook)
        before_sha = git_event.base_sha
        commit_sha = git_event.head_sha
        branch = git_event.head_branch
    else:
        git_event = NormalizedPush(**normalize_git_webhook)
        before_sha = git_event.before
        commit_sha = git_event.after
        branch = git_event.branch

    file_lifecycle = get_file_lifecycle(git_event=git_event, rule=rule, branch=branch)

    files_to_process = []
    files_to_prune = []

    # ============================================================================
    # SEPARATE FILES: Process vs Prune
    # ============================================================================
    for file_path, lifecycle in file_lifecycle.items():
        latest_status = lifecycle['latest_status']
        earliest_status = lifecycle['earliest_status']
        match_context = lifecycle['match_context']

        # Case 1: File was REMOVED - add to prune list
        if latest_status == FileStatus.REMOVED:
            if rule.prune or rule.pruneLast:
                files_to_prune.append({
                    'file_path': file_path,
                    'metadata': match_context
                })
                print(f"🗑️  Marked for prune: {file_path}")
            continue  # Skip normal processing

        # Case 2: File was ADDED or MODIFIED - process normally
        current_hash = commit_sha
        previous_hash = before_sha

        # If file was just added, no previous version
        if earliest_status == FileStatus.ADDED:
            previous_hash = None

        files_to_process.append({
            'file_path': file_path,
            'last_commit_hash': current_hash,
            'first_commit_hash': previous_hash,
            'match_context': match_context
        })

    if not files_to_process and not files_to_prune:
        return {'status': 'skipped', 'reason': 'no matching files'}

    # 3. Initialize Pipeline Components
    source = Source.create(**platform_config)
    sink = Sink.create(**datasource_config)
    sink.connect()

    parser = ContentParser()
    flattener = Flattenizer(root_key="varTrack")

    processed_files = 0
    total_rows_written = 0

    # 4. Fetch and Process Files (only if there are files to sync)
    if files_to_process:
        files_to_process = source.read(files_to_process, git_event.repository)

        for file in files_to_process:
            try:
                is_file_strategy = (datasource_config.get('update_strategy') == 'file')
                rows = calculate_sync_rows(
                    file=file,
                    rule=rule,
                    sink=sink,
                    parser=parser,
                    flattener=flattener,
                    is_file_strategy=is_file_strategy
                )

                for row in rows:
                    sink.write(row)
                    total_rows_written += 1

                processed_files += 1

            except Exception as e:
                print(f"⚠️ [Engine] Skipped file {file['file_path']}: {e}")

    # ============================================================================
    # 5. FLUSH STRATEGY
    # ============================================================================

    # If pruneLast=true AND we have files to prune: flush before pruning
    # Otherwise: flush now
    if files_to_prune and rule.pruneLast:
        if total_rows_written > 0:
            print(f"💾 [PruneLast] Flushing {total_rows_written} operations before prune...")
            sink.flush()
    else:
        if total_rows_written > 0:
            print(f"💾 Flushing {total_rows_written} operations...")
            sink.flush()

    # ============================================================================
    # 6. PRUNE OPERATIONS
    # ============================================================================

    pruned_files = 0
    protected_files = 0

    if files_to_prune:
        print(f"\n🗑️  Processing {len(files_to_prune)} prune operation(s)...")

        for file_info in files_to_prune:
            unique_key = file_info['metadata'].get('unique_key')

            # Check protection
            if rule.is_protected_from_prune(unique_key):
                protected_files += 1
                print(f"🛡️  PROTECTED: {unique_key}")
                continue

            try:
                if rule.dryRunPrune:
                    print(f"🔍 [DRY RUN] Would delete: {unique_key}")
                    pruned_files += 1
                else:
                    sink.delete(file_info['metadata'])
                    pruned_files += 1
                    print(f"✅ Pruned: {unique_key}")
            except Exception as e:
                print(f"❌ Failed to prune {unique_key}: {e}")

    sink.disconnect()

    return {
        'status': 'success',
        'processed_files': processed_files,
        'pruned_files': pruned_files,
        'protected_files': protected_files,
        'total_rows': total_rows_written,
    }