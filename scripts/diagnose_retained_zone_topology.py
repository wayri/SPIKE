# SPDX-License-Identifier: Apache-2.0
"""Inspect licensed retained filled paths without importing or moving geometry."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.hybrid_mesh import _clean_polygon, _signed_polygon_area
from python.spike_core.planar_polygon_topology import first_non_simple_edge_pair


def diagnose(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    rows = []
    for zone in data['selection']['zones']:
        points = list(map(tuple, zone['importer_normalized_filled_polygon_points_mm']))
        edges = Counter(zip(points, points[1:]+points[:1]))
        pair = first_non_simple_edge_pair(points)
        rows.append({
            'source_id': zone['source_id'], 'vertices': len(points),
            'repeated_vertices': len(points)-len(set(points)),
            'reverse_edge_pairs': sum(min(value, edges[(b, a)])
                                      for (a, b), value in edges.items() if a < b),
            'signed_area_mm2': _signed_polygon_area(points),
            'first_non_simple_pair': pair,
            'pair_edges_mm': [[points[i], points[(i+1) % len(points)]] for i in pair] if pair else [],
            'cleaned_first_non_simple_pair': first_non_simple_edge_pair(_clean_polygon(points)),
        })
    return {'contract': 'spike/retained-filled-path-topology-diagnostic/v1',
            'input_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'source_fixture': data['fixture'], 'rows': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Refusing to overwrite topology evidence.')
    result = diagnose(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps([{key: row[key] for key in ('source_id', 'repeated_vertices', 'reverse_edge_pairs')}
                      for row in result['rows']], indent=2))
