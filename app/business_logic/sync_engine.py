# app/business_logic/sync_engine.py
from typing import Dict, Any, List

from app.business_logic.json_pathmap import flatten_dfs
from app.utils.enums.sync_mode import SyncMode
from app.pipeline.pipeline_row import PipelineRow, RowKind
from app.business_logic.compare_states import compare_states

def calculate_sync_rows(
    file: Dict[str, Any],
    rule,
    sink,
    parser,
    flattener,
    is_file_strategy: bool
) -> List[PipelineRow]:
    """
    Orchestrates the state comparison and generates the necessary PipelineRows.
    """
    # A. Resolve Sync Mode (AUTO logic or explicit)
    sync_mode = rule.resolve_sync_mode(sink, file['current'], is_file_strategy)

    # B. Parse & Flatten Current Git State
    curr_flat = flattener.process(parser.process(file['current']))

    if rule.variablesMap:
        vars_to_sync = flatten_dfs(rule.variablesMap, as_kv=False)
        curr_flat.update(vars_to_sync)

    # C. Determine "Previous" State based on SyncMode
    if sync_mode == SyncMode.LIVE_STATE:
        db_raw = sink.fetch(file['metadata'])
        if is_file_strategy:
            prev_flat = flattener.process(parser.process(db_raw))
        else:
            prev_flat = db_raw or {}
    else:
        # Standard: Compare against the actual previous commit content
        prev_flat = flattener.process(parser.process(file['previous']))

    # D. Generate Diff
    diff = compare_states(current_data=curr_flat, old_data=prev_flat)
    rows = []

    # Map standard changes to PipelineRows
    for kind, entries in [
        (RowKind.INSERT, diff['added']),
        (RowKind.UPDATE, diff['changed']),
        (RowKind.DELETE, diff['deleted'])
    ]:
        for k, v in entries.items():
            rows.append(PipelineRow(key=k, value=v, kind=kind, metadata=file['metadata']))

    # E. Handle "Unchanged" data for specific modes (Upsert All / Smart Repair)
    if sync_mode == SyncMode.GIT_UPSERT_ALL:
        for k, v in diff['unchanged'].items():
            rows.append(PipelineRow(key=k, value=v, kind=RowKind.UPDATE, metadata=file['metadata']))

    elif sync_mode == SyncMode.GIT_SMART_REPAIR:
        db_raw = sink.fetch(file['metadata'])
        db_state = flattener.process(parser.process(db_raw)) if is_file_strategy else (db_raw or {})
        for k, v in diff['unchanged'].items():
            if k not in db_state or db_state[k] != v:
                rows.append(PipelineRow(key=k, value=v, kind=RowKind.UPDATE, metadata=file['metadata']))

    return rows