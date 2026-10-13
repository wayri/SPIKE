# SPDX-License-Identifier: Apache-2.0
"""Explicit electrical exclusion of provenance-bound thermal package bodies."""
import re


def thermal_only_parts(raw, assembly, error):
    selected = raw.get('thermal_only_part_ids', [])
    if not isinstance(selected, list) or len(selected) > 100 or any(
            not isinstance(item, str) or not item or item != item.strip() for item in selected):
        raise error('thermal_only_part_ids requires a bounded list of retained component part IDs.')
    if len(set(selected)) != len(selected):
        raise error('Duplicate thermal-only component part.')
    boards = {board.id: board for board in assembly.boards}
    parts = {part.id: part for part in assembly.parts}
    for pid in selected:
        part = parts.get(pid)
        provenance = part.extensions.get('spike.thermal-component') if part is not None else None
        if (part is None or part.part_type != 'component' or not part.model_id or
                not isinstance(provenance, dict) or provenance.get('contract') != 'spike/thermal-component-provenance/v1'):
            raise error('Thermal-only parts must be explicitly promoted retained component bodies.')
        board = boards.get(provenance.get('board_occurrence_id'))
        if (board is None or part.frame.parent_frame_id != board.frame.frame_id or
                provenance.get('design_id') != board.design_id or provenance.get('model_id') != part.model_id or
                not isinstance(provenance.get('component_id'), str) or not provenance['component_id'] or
                part.source_id != provenance['component_id']):
            raise error('Thermal-only component source identity or owning board frame disagrees.')
        for key in ('component_digest', 'design_source_digest', 'model_digest', 'source_sha256'):
            if not isinstance(provenance.get(key), str) or not re.fullmatch('[0-9a-f]{64}', provenance[key]):
                raise error('Thermal-only component requires complete source provenance digests.')
        for bond in assembly.electrical_bonds:
            if any(endpoint == pid or endpoint.startswith(pid+':') for endpoint in (bond.endpoint_a, bond.endpoint_b)):
                raise error('Thermal-only part cannot be an endpoint of a retained electrical bond.')
    return selected
