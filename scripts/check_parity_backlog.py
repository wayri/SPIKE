# SPDX-License-Identifier: Apache-2.0
"""Check development backlog coverage and fixture integrity, without running physics."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

if __package__:
    from .benchmark_board_corpus import validate_entry
    from .parity_stage_evidence import validate_stages
else:
    from benchmark_board_corpus import validate_entry
    from parity_stage_evidence import validate_stages

ROOT = Path(__file__).resolve().parents[1]


def validate_backlog(payload: dict, roadmap: str, root: Path = ROOT) -> dict:
    if not isinstance(payload, dict) or payload.get('contract') != 'spike/parity-development-backlog/v1':
        raise ValueError('unsupported development backlog')
    items = payload.get('items')
    if not isinstance(items, list) or not items:
        raise ValueError('backlog requires items')
    expected = re.findall(r'^\| ((?:SI|PI|SA|AMS|EM|TH|WF)\d{2}) \|', roadmap, re.MULTILINE)
    if not expected or len(expected) != len(set(expected)):
        raise ValueError('roadmap capability IDs must be unique and non-empty')
    ids = []
    benchmark_definitions_pending = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('backlog items must be objects')
        for field in ('id', 'title', 'owner_role', 'baseline', 'target', 'priority'):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f'missing {field}')
        ids.append(item['id'])
        if item.get('status') not in ('planned', 'in_progress', 'blocked', 'complete'):
            raise ValueError('unrecognized development status')
        gaps = item.get('open_gaps')
        if not isinstance(gaps, list) or any(not isinstance(gap, str) or not gap.strip() for gap in gaps):
            raise ValueError('open_gaps must contain non-empty strings')
        if item['status'] == 'complete' and gaps:
            raise ValueError('complete item retains open gaps')
        evidence = item.get('baseline_evidence')
        if not isinstance(evidence, list) or not evidence:
            raise ValueError('baseline evidence is required')
        for link in evidence:
            if not isinstance(link, str):
                raise ValueError('evidence paths must be strings')
            path = (root / 'docs' / link.split('#')[0]).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError(f'missing or out-of-project evidence: {link}')
        benchmark = item.get('benchmark')
        if not isinstance(benchmark, dict) or not isinstance(benchmark.get('acceptance'), str) or not benchmark['acceptance'].strip():
            raise ValueError('benchmark acceptance is required')
        if benchmark.get('status') == 'definition_pending':
            benchmark_definitions_pending.append(item['id'])
            if item['status'] == 'complete':
                raise ValueError('complete item lacks benchmark definition')
        elif benchmark.get('status') == 'implemented_bounded':
            name = benchmark.get('manifest')
            if not isinstance(name, str):
                raise ValueError('implemented benchmark requires manifest')
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError('benchmark manifest must be inside project')
            boards = json.loads(path.read_text(encoding='utf-8'))['boards']
            if not isinstance(boards, list) or not 1 <= len(boards) <= 100:
                raise ValueError('benchmark requires bounded board fixtures')
            for board in boards:
                validate_entry(board, path.parent)
        else:
            raise ValueError('unrecognized benchmark status')
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError('backlog IDs must match roadmap exactly without duplicates')
    done_stages = validate_stages(payload.get('stages', []), ids, root)
    return {'items': len(ids), 'benchmark_definitions_pending': benchmark_definitions_pending,
            'done_stages': done_stages,
            'scope': 'Backlog coverage and fixture integrity only; no runtime capability promotion.'}


def main() -> int:
    try:
        result = validate_backlog(json.loads((ROOT / 'docs/parity-capability-backlog-v1.json').read_text()),
                                  (ROOT / 'docs/HYPERLYNX_PARITY_AND_MULTIPHYSICS_PLAN.md').read_text())
    except (ValueError, OSError, KeyError) as error:
        print(f'Parity backlog check failed: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
