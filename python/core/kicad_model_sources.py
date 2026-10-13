# SPDX-License-Identifier: Apache-2.0
"""Retain KiCad model declarations without composing placement transforms."""
from __future__ import annotations

import math


def model_sources(footprint: list) -> list[dict]:
    result = []
    for node in footprint:
        if not isinstance(node, list) or not node or node[0] != 'model':
            continue
        row = {'source_node': node, 'ordinal': len(result),
               'uri': str(node[1]).strip('"') if len(node) > 1 and isinstance(node[1], str) else '',
               'semantic_state': 'source_placement_unapplied', 'projection': 'forbidden',
               'declared_vectors': {}, 'errors': []}
        if not row['uri']:
            row['errors'].append('missing model URI')
        for key in ('offset', 'scale', 'rotate'):
            declarations = [n for n in node[2:] if isinstance(n, list) and n and n[0] == key]
            if not declarations:
                continue
            try:
                if len(declarations) != 1 or len(declarations[0]) != 2:
                    raise ValueError('expected exactly one xyz declaration')
                vector = declarations[0][1]
                if not isinstance(vector, list) or len(vector) != 4 or vector[0] != 'xyz':
                    raise ValueError('expected three xyz values')
                values = [float(v) for v in vector[1:]]
                if any(not math.isfinite(v) for v in values):
                    raise ValueError('nonfinite xyz value')
                row['declared_vectors'][key] = values
            except (ValueError, TypeError, OverflowError) as error:
                row['errors'].append(f'{key}: {error}')
        row['valid_source_vectors'] = not row['errors']
        result.append(row)
    return result
