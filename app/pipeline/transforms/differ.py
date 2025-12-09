from typing import List, Dict, Any
from app.pipeline.core import Transform
from app.pipeline.models import PipelineRow, RowKind
from app.business_logic.compare_states import compare_states


class DiffExploder(Transform):
    """
    Compares Previous vs Current state and emits a stream of PipelineRows.
    """

    def process(self, current: Dict[str, Any], previous: Dict[str, Any], metadata: Dict[str, Any]) -> List[PipelineRow]:
        rows = []

        # Use existing comparison logic
        diff = compare_states(current_data=current, old_data=previous)

        # 1. RowKind.INSERT
        for key, value in diff['added'].items():
            rows.append(PipelineRow(
                key=key,
                value=value,
                kind=RowKind.INSERT,
                metadata=metadata
            ))

        # 2. RowKind.UPDATE
        # diff['changed'] structure: { key: {'old': val, 'new': val} }
        for key, change in diff['changed'].items():
            rows.append(PipelineRow(
                key=key,
                value=change['new'],
                kind=RowKind.UPDATE,
                metadata=metadata
            ))

        # 3. RowKind.DELETE
        for key, value in diff['deleted'].items():
            rows.append(PipelineRow(
                key=key,
                value=value,  # Value helps for logging, but usually redundant for delete
                kind=RowKind.DELETE,
                metadata=metadata
            ))

        return rows