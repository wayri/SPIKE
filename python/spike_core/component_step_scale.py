# SPDX-License-Identifier: Apache-2.0
"""Bounded explicit derived STEP assets; scale geometry, never placement frames."""
from __future__ import annotations

import base64
import hashlib
import json
import math
from pathlib import Path
import tempfile

from .mcad_importer import validate_step_mcad_artifact
from .mcad_tessellation import _freecad_path
from .sparselizard_process import run_adapter_process

MAX_BYTES = 16 * 1024**2


def validate_scale(scale_xyz):
    if (not isinstance(scale_xyz, (list, tuple)) or len(scale_xyz) != 3
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                   or not 1e-3 <= v <= 1e3 for v in scale_xyz)
            or max(scale_xyz) / min(scale_xyz) > 1e6):
        raise ValueError('STEP_SCALE: three finite positive factors in [1e-3,1e3], ratio <=1e6 required')
    return [float(v) for v in scale_xyz]


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('STEP_SCALE_NATIVE: invalid native number')
    return float(value)


def _close(actual, expected, *, volume=False):
    expected = _number(expected)
    if not math.isclose(_number(actual), expected, rel_tol=1e-8 if volume else 1e-9,
                        abs_tol=0. if volume else 2e-6):
        raise ValueError('STEP_SCALE_NATIVE: volume or bounds differ from scaling oracle')


def validate_facts(facts, source_sha, output_sha, scale):
    if (facts.get('contract') != 'spike/scaled-step-native/v1' or facts.get('source_sha256') != source_sha
            or facts.get('output_sha256') != output_sha or facts.get('scale_xyz') != scale
            or facts.get('units') != 'mm' or facts.get('solver_qualified') is not False):
        raise ValueError('STEP_SCALE_NATIVE: native provenance mismatch')
    for key in ('source', 'scaled', 'roundtrip'):
        row = facts.get(key, {})
        if (isinstance(row.get('solid_count'), bool) or row.get('solid_count') != 1
                or row.get('valid') is not True or row.get('closed') is not True):
            raise ValueError('STEP_SCALE_NATIVE: exactly one valid closed solid required')
        if _number(row.get('volume_mm3')) <= 0 or len(row.get('bounds_mm', [])) != 6:
            raise ValueError('STEP_SCALE_NATIVE: missing volume/bounds')
        for value in row['bounds_mm']:
            _number(value)
    source = facts['source']
    expected_volume = source['volume_mm3'] * math.prod(scale)
    expected_bounds = [v * scale[i % 3] for i, v in enumerate(source['bounds_mm'])]
    for key in ('scaled', 'roundtrip'):
        _close(facts[key]['volume_mm3'], expected_volume, volume=True)
        for a, b in zip(facts[key]['bounds_mm'], expected_bounds):
            _close(a, b)


def scale_component_step(source_step, scale_xyz, *, expected_sha256,
                         freecad_executable=None, cancellation_event=None):
    """Return embedded derived geometry and provenance; no caller path is written."""
    scale = validate_scale(scale_xyz)
    if not isinstance(source_step, bytes) or not 0 < len(source_step) <= MAX_BYTES:
        raise ValueError('STEP_SCALE: source STEP must be 1..16 MiB of bytes')
    sha = hashlib.sha256(source_step).hexdigest()
    if sha != expected_sha256:
        raise ValueError('STEP_SCALE_STALE: source bytes differ from retained digest')
    validate_step_mcad_artifact(source_step)
    executable = _freecad_path(freecad_executable)
    with tempfile.TemporaryDirectory(prefix='spike-step-scale-') as folder:
        root = Path(folder)
        (root/'source.step').write_bytes(source_step)
        (root/'request.json').write_text(json.dumps({'source_sha256': sha, 'scale_xyz': scale}))
        (root/'scale.py').write_bytes(Path(__file__).with_name('freecad_scale_step.py').read_bytes())
        stdin = ("scope={'__name__':'spike_step_scale'}\n"
                 "exec(compile(open('scale.py',encoding='utf-8').read(),'scale.py','exec'),scope)\n"
                 "scope['scale_step']('.')\nraise SystemExit(0)\n").encode()
        result = run_adapter_process([str(executable), '--console', '--user-cfg', str(root/'user.cfg'),
                                      '--system-cfg', str(root/'system.cfg')], cwd=root,
                                     timeout_s=90, memory_limit_mb=4096, output_limit_bytes=MAX_BYTES + 1024**2,
                                     stream_limit_bytes=1024**2, stdin_payload=stdin,
                                     cancellation_event=cancellation_event)
        output, fact_file = root/'scaled.step', root/'facts.json'
        if result['return_code'] or not output.is_file() or not fact_file.is_file():
            raise RuntimeError('STEP_SCALE_NATIVE: preprocessing failed; no derived asset accepted: ' +
                               (str(result.get('stderr', '')) + str(result.get('stdout', '')))[-2000:])
        if not 0 < output.stat().st_size <= MAX_BYTES or not 0 < fact_file.stat().st_size <= 1024**2:
            raise ValueError('STEP_SCALE_NATIVE: derived output budget exceeded')
        data = output.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        validate_step_mcad_artifact(data)
        facts = json.loads(fact_file.read_text())
        validate_facts(facts, sha, digest, scale)
    return {'contract': 'spike/scaled-component-step/v1', 'units': 'mm',
            'geometry': {'type': 'step', 'data_base64': base64.b64encode(data).decode(), 'sha256': digest},
            'source_sha256': sha, 'scale_xyz': scale, 'native_facts': facts,
            'material_qualified': False, 'solver_ready': False,
            'placement_scaled': False, 'review_required': True}
