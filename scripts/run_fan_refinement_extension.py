# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Fixed extra fan CHT refinement cases; isolated local evidence, not promotion."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.openfoam_fan_fixture import build_fan_heated_fixture
from python.spike_core.openfoam_multiregion_execution import load_verified_runnable_case, run_multiregion_case
from python.spike_core.sparselizard_process import run_adapter_process
from scripts.fan_wsl_scratch import ScratchRunner

SETTINGS = {'time16': (4, .016), 'time8': (4, .008), 'mesh16': (16, .001)}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def file_digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'build/fan-refinement-extension-20260907')
    parser.add_argument('--cases', nargs='+', default=list(SETTINGS))
    args = parser.parse_args()
    if len(set(args.cases)) != len(args.cases) or any(name not in SETTINGS for name in args.cases):
        parser.error('Cases must be unique fixed names: time16, time8, mesh16')
    args.output.mkdir(parents=True, exist_ok=False)
    source_paths = [p for p in (ROOT/'python/spike_core').glob('openfoam*.py')
                    if 'validation' not in p.name and 'refinement_study' not in p.name]
    source_paths += [Path(__file__), ROOT/'scripts/fan_wsl_scratch.py',
                     ROOT/'python/spike_core/sparselizard_process.py']
    def source_hashes():
        return {str(path.relative_to(ROOT)): file_digest(path) for path in source_paths}
    initial = source_hashes()
    report = {'contract': 'spike/fan-cht-study-run/v1', 'machine': platform.platform(),
              'python': sys.version, 'source_hashes': initial, 'end_time_s': 10.0,
              'production_qualified': False, 'cases': {}}
    for name in args.cases:
        divisions, dt = SETTINGS[name]
        root = args.output/name
        print(f'Preparing {name}: divisions={divisions}, dt={dt}, end=10 s', flush=True)
        fixture = build_fan_heated_fixture(root, divisions=divisions, board_count=1,
                                           delta_t_s=dt, end_time_s=10.0,
                                           write_interval_steps=round(10.0/dt))
        (root/'fixture.json').write_text(json.dumps(fixture, indent=2, allow_nan=False), encoding='utf-8')
        count = 0
        def runner(command, **kwargs):
            nonlocal count
            count += 1
            print(f'{name}: command {count}', flush=True)
            kwargs['stream_limit_bytes'] = 128*1024**2
            result = run_adapter_process(command, **kwargs)
            (root/f'command-{count:02d}.json').write_text(
                json.dumps({'argv': command, **result}, indent=2, allow_nan=False), encoding='utf-8')
            return result
        active_runner = ScratchRunner(root/'case', runner)
        result = run_multiregion_case(root/'case', timeout_s=900, runner=active_runner)
        (root/'result.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
        report['cases'][name] = {'divisions': divisions, 'time_step_s': dt, 'board_count': 1,
            'case_sha256': load_verified_runnable_case(root/'case')[1]['manifest_digest'],
            'fixture_sha256': digest(fixture), 'result_sha256': digest(result),
            'status': result['status'], 'summary': result.get('summary'),
            'duration_s': result.get('duration_s'), 'message': result.get('message'),
            'retained_linux_scratch': active_runner.remote}
        # Include all generated input/output bytes, not only bounded summaries.
        artifacts = {str(path.relative_to(root)): file_digest(path)
                     for path in sorted(root.rglob('*')) if path.is_file()}
        (root/'artifact-sha256.json').write_text(json.dumps(artifacts, indent=2), encoding='utf-8')
        report['cases'][name]['artifact_manifest_sha256'] = file_digest(root/'artifact-sha256.json')
        report['sources_unchanged'] = initial == source_hashes()
        (args.output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
        (args.output/'report.sha256').write_text(file_digest(args.output/'report.json')+'\n', encoding='ascii')
        print(json.dumps({'case': name, **report['cases'][name]}), flush=True)
        if result['status'] != 'completed' or not report['sources_unchanged']:
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
