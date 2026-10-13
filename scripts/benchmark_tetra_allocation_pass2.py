# SPDX-License-Identifier: Apache-2.0
"""Alternating-order exact-candidate benchmark for the second allocation pass."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_internal_mesher import fixture_corpus
from python.spike_core import internal_tetra_generation as current

BASELINE_SHA256 = '773708649885455223e6543ad80fecddc274c9c7d1150515ba756c26926be1d5'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def load_baseline(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != BASELINE_SHA256:
        raise ValueError('Baseline source does not match the saved first-pass fingerprint.')
    spec = importlib.util.spec_from_file_location('python.spike_core._allocation_pass2_baseline', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def outcome(module, points):
    started = time.perf_counter_ns()
    try:
        result = module.generate_tetra_mesh(points)
    except module.TetraGenerationError as error:
        elapsed = time.perf_counter_ns() - started
        return {'status': 'rejected', 'type': type(error).__name__, 'message': str(error)}, elapsed
    elapsed = time.perf_counter_ns() - started
    return {'status': 'completed', 'candidate': result}, elapsed


def run(baseline, samples=5):
    rows = []
    for fixture in fixture_corpus():
        points = fixture['points']
        original = canonical(points)
        expected, _ = outcome(baseline, points)
        warm, _ = outcome(current, points)
        if expected != warm:
            raise AssertionError(f"Warmup candidate/rejection mismatch: {fixture['id']}")
        timings = {'baseline': [], 'current': []}
        for sample in range(samples):
            order = ('baseline', 'current') if sample % 2 == 0 else ('current', 'baseline')
            for name in order:
                result, elapsed = outcome(baseline if name == 'baseline' else current, points)
                if result != expected or canonical(points) != original:
                    raise AssertionError(f"Candidate, rejection or input changed: {fixture['id']}")
                timings[name].append(elapsed)
        medians = {name: statistics.median(values) for name, values in timings.items()}
        row = {'fixture': fixture['id'], 'points_sha256': fixture['points_sha256'],
               'point_count': len(points), 'status': expected['status'],
               'exact_candidate_or_rejection': True, 'samples_ns': timings,
               'median_ns': medians,
               'outcome_sha256': hashlib.sha256(canonical(expected)).hexdigest()}
        if expected['status'] == 'completed':
            row.update(speedup=medians['baseline']/medians['current'],
                       counts=expected['candidate']['mesh']['counts'],
                       quality=expected['candidate']['quality'],
                       predicate_evidence=expected['candidate']['evidence'])
        else:
            row['rejection'] = {key: value for key, value in expected.items() if key != 'status'}
        rows.append(row)
    return {'contract': 'spike/tetra-allocation-pass2-benchmark/v1',
            'status': 'passed', 'samples': samples, 'warmups_per_backend': 1,
            'timing_scope': 'generation including mandatory certification; excludes result comparison',
            'execution': 'alternating order in one process; no process-RAM comparison',
            'platform': platform.platform(), 'python': sys.version,
            'baseline_sha256': BASELINE_SHA256,
            'current_sha256': hashlib.sha256((ROOT/'python/spike_core/internal_tetra_generation.py').read_bytes()).hexdigest(),
            'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'rows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=ROOT/'output/mesher-pass2-20261012/baseline-generation.py')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--samples', type=int, choices=(5, 7), default=5)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Refusing to overwrite benchmark evidence.')
    result = run(load_baseline(args.baseline), args.samples)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'status': result['status'], 'rows': [
        {key: row[key] for key in ('fixture', 'status', 'median_ns', 'exact_candidate_or_rejection')}
        for row in result['rows']]}, indent=2))


if __name__ == '__main__':
    main()
