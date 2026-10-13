# SPDX-License-Identifier: Apache-2.0
"""Check the actionable backlog without asserting numerical qualification."""
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / 'docs/solver-improvement-actions-v1.json').read_text(encoding='utf-8'))
    assert data['contract'] == 'spike/solver-improvement-actions/v1'
    assert data['all_solver_qualified'] is False
    actions = data['actions']
    by_id = {a['id']: a for a in actions}
    assert len(by_id) == len(actions) == 16
    assert (root / data['plan_document']).is_file()
    plan = (root / data['plan_document']).read_text(encoding='utf-8')
    for a in actions:
        assert a['status'] in ('planned', 'in_progress', 'blocked', 'completed')
        assert f"### {a['id']} {a['title']}" in plan
        assert a['instructions_and_completion_gates'] in plan
        assert a['owner_role'] and 1 <= a['stage'] <= 5
        assert all((root / p).is_file() for p in a['primary_paths'])
        assert all(d in by_id and d != a['id'] for d in a['depends_on'])
        if a['status'] == 'completed':
            assert a['execution_evidence'], 'Completion needs actual execution evidence'
    def visit(identifier, stack):
        assert identifier not in stack, 'Dependency cycle'
        for dependency in by_id[identifier]['depends_on']:
            visit(dependency, stack | {identifier})
    for identifier in by_id:
        visit(identifier, set())
    assert all(a in by_id for a in data['first_batch'] + data['parallel_analysis'])
    print('16 solver actions checked: ownership, paths, gates, dependencies and claim boundaries')


if __name__ == '__main__':
    main()
