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
COUPLED_EXPANSION_SCOPE = frozenset({
    'GP01', 'GP02', 'GP03', 'GP04', 'GP05', 'GP06', 'GP07', 'GP09', 'GP10', 'GP11',
    'GP12', 'GP13', 'GP14', 'GP15', 'GP16',
    'VF01', 'VF02', 'AX01', 'LB01', 'LB02',
})
RESTRICTED_EXPANSION_SCOPES = {'GP05': 'vehicle_aerodynamics'}


def validate_backlog(payload: dict, roadmap: str, root: Path = ROOT) -> dict:
    if not isinstance(payload, dict) or payload.get('contract') != 'spike/parity-development-backlog/v1':
        raise ValueError('unsupported development backlog')
    items = payload.get('items')
    if not isinstance(items, list) or not items:
        raise ValueError('backlog requires items')
    expected = re.findall(r'^\| ((?:SI|PI|SA|AMS|EM|TH|WF|GP|OP|VF|AX|LB|RF|PW)\d{2}) \|', roadmap, re.MULTILINE)
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
    policy = payload.get('execution_policy', {})
    post_ids = {name for name in ids if name[:2] in {'GP', 'OP', 'VF', 'AX', 'LB', 'RF', 'PW'}}
    parity_ids = set(ids) - post_ids
    if (policy.get('active_phase') not in {'parity', 'post_parity'}
            or set(policy.get('parity_capabilities', [])) != parity_ids
            or set(policy.get('post_parity_capabilities', [])) != post_ids):
        raise ValueError('execution policy must preserve parity/post-parity scope')
    by_id = {item['id']: item for item in items}
    pisi_ids = {name for name in parity_ids if name.startswith(('PI', 'SI'))}
    if (policy.get('active_priority') != 'pi_si_stack'
            or set(policy.get('priority_capabilities', [])) != pisi_ids):
        raise ValueError('PI/SI priority must cover the complete PI/SI stack')
    parity_complete = all(by_id[name]['status'] == 'complete' for name in parity_ids)
    if policy['active_phase'] == 'post_parity' and not parity_complete:
        raise ValueError('post-parity phase requires established parity completion')
    expansion = policy.get('parallel_expansion', {})
    allowed = set()
    if expansion:
        if (not isinstance(expansion, dict) or expansion.get('enabled') is not True
                or expansion.get('requested_on') != '2026-10-18'
                or not isinstance(expansion.get('authorization'), str)
                or not expansion['authorization'].strip()
                or not isinstance(expansion.get('capability_ids'), list)
                or len(expansion['capability_ids']) != len(set(expansion['capability_ids']))
                or set(expansion['capability_ids']) != COUPLED_EXPANSION_SCOPE
                or expansion.get('restricted_scopes') != RESTRICTED_EXPANSION_SCOPES):
            raise ValueError('parallel expansion must preserve explicitly requested coupled scope')
        allowed = COUPLED_EXPANSION_SCOPE
    if policy['active_phase'] == 'parity':
        for stage in payload.get('stages', []):
            capability = stage.get('capability_id')
            if (capability in RESTRICTED_EXPANSION_SCOPES and capability in allowed
                    and stage.get('status') != 'planned'
                    and stage.get('scope') != RESTRICTED_EXPANSION_SCOPES[capability]):
                raise ValueError('parallel vehicle aerodynamics scope cannot authorize general CFD')
        if (any(by_id[name]['status'] != 'planned' for name in post_ids - allowed)
                or any(stage.get('status') != 'planned' for stage in payload.get('stages', [])
                       if stage.get('capability_id') in post_ids - allowed)):
            raise ValueError('post-parity work must remain deferred during parity')
    done_stages = validate_stages(payload.get('stages', []), ids, root)
    return {'items': len(ids), 'benchmark_definitions_pending': benchmark_definitions_pending,
            'done_stages': done_stages,
            'active_phase': policy['active_phase'], 'post_parity_gate_open': parity_complete,
            'parallel_expansion': sorted(allowed),
            'restricted_expansion_scopes': RESTRICTED_EXPANSION_SCOPES if allowed else {},
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
