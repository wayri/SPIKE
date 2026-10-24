# SPDX-License-Identifier: Apache-2.0
"""Gate SI08-S05 software evidence using explicitly trusted native observations.

Artifact identities and sampled algebra are checked independently. A native
observation is a trusted agent/human record; pixels do not certify physics.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import re
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_multiport_integration import SOURCES as INTEGRATION_SOURCES
from scripts.verify_multiport_integration import digest, retained_path, validate_receipt as integration_validate
from python.spike_core.sparameter_sampling import _digest
from python.spike_core.contract_catalog import schema_operation

SOURCES = INTEGRATION_SOURCES
VALIDATOR_SOURCES = ('scripts/parity_multiport_native_gate.py',
                     'tests/python/test_multiport_native_evidence.py')
ARTIFACTS = ('request', 'capture', 'wide_image', 'wide_uia', 'narrow_image',
             'narrow_uia', 'invalidation_uia', 'failure_uia', 'recovery_uia')
EXTERNAL = [f'External-{i}-reviewed-reference-plane-with-long-connector-identity' for i in range(1, 4)]
DUT = [f'DUT-{i}-retained-device-port-with-long-assembly-identity' for i in range(1, 4)]
EXPECTED = [[.1, .2, -.1], [.05, .15, .3], [.2, -.05, .1]]


def require(value, message):
    if not value:
        raise ValueError(message)


def read_json(path):
    def bad_constant(value):
        raise ValueError('Nonfinite JSON constant: ' + value)
    return json.loads(path.read_text(encoding='utf-8-sig'), parse_constant=bad_constant)


def binding(path, root=ROOT):
    path = path.resolve()
    require(path.is_relative_to(root.resolve()), 'Artifact must be inside repository')
    return {'path': path.relative_to(root.resolve()).as_posix(), 'sha256': digest(path)}


def bound_path(record, root):
    require(isinstance(record, dict) and set(record) == {'path', 'sha256'}, 'Invalid artifact binding')
    path = retained_path(root, record['path'])
    require(path.stat().st_size <= 32*1024*1024, 'Artifact exceeds 32 MiB')
    require(digest(path) == record['sha256'], 'Artifact hash differs')
    return path


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def matrix_equal(actual, wanted):
    require(isinstance(actual, list) and len(actual) == len(wanted), 'Matrix row count')
    for row, expected in zip(actual, wanted):
        require(isinstance(row, list) and len(row) == len(expected), 'Matrix column count')
        for pair, value in zip(row, expected):
            require(isinstance(pair, dict) and set(pair) == {'real', 'imag'}
                    and all(finite_number(pair[key]) for key in pair), 'Nonfinite or malformed matrix entry')
            require(abs(pair['real']-value) <= 2e-12 and abs(pair['imag']) <= 2e-12,
                    'Independent matched-path oracle differs')


def validate_capture(request, capture):
    require(isinstance(capture, dict) and set(capture) == {'source', 'result'}, 'Invalid native capture')
    result = capture['result']
    require(capture['source'] == request == result.get('source_request'), 'Native source identity differs')
    for kind, document in (('request', request), ('result', result)):
        require(schema_operation('validate', {'name': f'multiport-deembedding-{kind}-v1.schema.json',
                                               'document': document})['valid'], 'Native contract malformed')
    # JavaScript JSON transport may encode integral floats as integers. Bind
    # the exact exported worker input, while equality above preserves values.
    require(result['input_digest'] == _digest(capture['source']), 'Canonical source digest differs')
    require(request['external_ports'] == EXTERNAL and request['dut_ports'] == DUT, 'Original long named maps required')
    fixture = [[0.]*6 for _ in range(6)]
    for i in range(3):
        fixture[i][i+3] = fixture[i+3][i] = .8
    for key, ports in (('measured', EXTERNAL), ('fixture', EXTERNAL+DUT)):
        source = request[key]
        require(source['port_names'] == ports and source['frequencies_hz'] == [0, 1e6]
                and source['reference_impedance_ohm'] == 50 and len(source['s_parameters']) == 2,
                'Original demonstration source contract differs')
        for sample in source['s_parameters']:
            matrix_equal(sample, fixture if key == 'fixture' else [[.64*v for v in row] for row in EXPECTED])
    derived = result['derived_network']
    require(derived['port_names'] == DUT and derived['frequencies_hz'] == [0, 1e6]
            and derived['reference_impedance_ohm'] == 50 and len(derived['s_parameters']) == 2,
            'Derived source indexing differs')
    for sample in derived['s_parameters']:
        matrix_equal(sample, EXPECTED)
    require(result['production_qualified'] is False and result['model_status'] == 'experimental'
            and len(result['diagnostics']) == 2, 'Unsupported result scope')
    for frequency, diagnostic in zip([0, 1e6], result['diagnostics']):
        require(diagnostic['frequency_hz'] == frequency
                and all(finite_number(v) for v in diagnostic.values()), 'Invalid diagnostics')


def normalized(path):
    text = path.read_text(encoding='utf-8-sig')
    # Native UIA splits inline React numbers and labels into separate text
    # nodes. Remove their tree indices/roles, preserving the observed values.
    text = re.sub(r'(?m)^[ \t]*\d+ (?:text|heading) ', '', text)
    return re.sub(r'\s+', ' ', text)


def retained_result(text):
    return ('Experimental result retained' in text and '3 DUT ports;' in text
            and '2 complete diagnostic samples' in text)


def disabled_export(text):
    return bool(re.search(r'button\s+\([^)]*disabled[^)]*\)\s+Export source and result', text, re.I)
                or re.search(r'button[^\n]{0,30}Export source and result[^\n]{0,30}disabled', text, re.I))


def validate_native(manifest, root=ROOT):
    require(manifest.get('contract') == 'spike/multiport-native-observation/v1'
            and manifest.get('stage_id') == 'SI08-S05'
            and manifest.get('family_complete') is False
            and manifest.get('production_qualified') is False, 'Invalid native scope')
    observation = manifest.get('observation', {})
    require(observation.get('kind') in ('trusted_agent_native_ui', 'trusted_human_native_ui')
            and all(isinstance(observation.get(key), str) and observation[key].strip()
                    for key in ('observer', 'observed_at_utc', 'statement')), 'Explicit trusted observation required')
    before = manifest.get('sources_before')
    require(isinstance(before, dict) and set(before) == set(SOURCES)
            and before == manifest.get('sources_after'), 'Native source coverage or drift')
    for name, value in before.items():
        require(digest(retained_path(root, name)) == value, 'Stale native source: '+name)
    artifacts = manifest.get('artifacts', {})
    require(set(artifacts) == set(ARTIFACTS), 'Missing native artifacts')
    paths = {key: bound_path(value, root) for key, value in artifacts.items()}
    require(len(set(paths.values())) == len(paths), 'Native artifacts must be distinct')
    validate_capture(read_json(paths['request']), read_json(paths['capture']))
    for label in ('wide', 'narrow'):
        with Image.open(paths[label+'_image']) as image:
            width, height = image.size
            require(image.format == 'JPEG' and height >= 600
                    and (width >= 1200 if label == 'wide' else 900 <= width <= 1100),
                    'Native screenshot dimensions/format differ')
            image.verify()
        text = normalized(paths[label+'_uia'])
        require(retained_result(text) and all(name in text for name in EXTERNAL+DUT),
                'Native retained-result/long-port observation missing')
    invalidated = normalized(paths['invalidation_uia'])
    require(disabled_export(invalidated) and 'Experimental result retained' not in invalidated,
            'Native invalidation evidence incomplete')
    failed = normalized(paths['failure_uia'])
    require(disabled_export(failed) and 'Experimental result retained' not in failed
            and 'alert' in failed.lower() and re.search(r'MULTIPORT_DEEMBEDDING_[A-Z_]+', failed),
            'Native structured failure evidence incomplete')
    require(retained_result(normalized(paths['recovery_uia'])), 'Native recovery evidence incomplete')


def validate_evidence(receipt, root=ROOT):
    require(receipt.get('contract') == 'spike/multiport-native-stage-evidence/v1'
            and receipt.get('stage_id') == 'SI08-S05' and receipt.get('status') == 'passed'
            and receipt.get('stage_complete') is True and receipt.get('native_visual_verified') is True
            and receipt.get('worker_schema_verified') is True and receipt.get('headless_desktop_verified') is True
            and receipt.get('family_complete') is False and receipt.get('production_qualified') is False,
            'Invalid or promoted native stage scope')
    require(receipt.get('validator_sources') == {
        name: digest(retained_path(root, name)) for name in VALIDATOR_SOURCES
    }, 'Stale native evidence validator')
    integration = read_json(bound_path(receipt.get('integration'), root))
    integration_validate(integration, root)
    native = read_json(bound_path(receipt.get('manifest'), root))
    validate_native(native, root)
    require(receipt.get('sources_before') == native['sources_before']
            and receipt.get('sources_after') == native['sources_after'], 'Stage source identity differs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('output', 'manifest', 'integration'):
        parser.add_argument('--'+option, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT):
        parser.error('Choose a fresh repository output path')
    integration = read_json(args.integration)
    integration_validate(integration)
    manifest = read_json(args.manifest)
    validate_native(manifest)
    receipt = {'contract': 'spike/multiport-native-stage-evidence/v1', 'stage_id': 'SI08-S05',
               'status': 'passed', 'stage_complete': True, 'family_complete': False,
               'production_qualified': False, 'native_visual_verified': True,
               'worker_schema_verified': True, 'headless_desktop_verified': True,
               'integration': binding(args.integration), 'manifest': binding(args.manifest),
               'validator_sources': {name: digest(ROOT/name) for name in VALIDATOR_SOURCES},
               'sources_before': manifest['sources_before'], 'sources_after': manifest['sources_after'],
               'scope': 'Software-stage gate only; native observation trusted, artifacts and sampled algebra verified; no physical qualification'}
    validate_evidence(receipt)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({'status': 'passed', 'stage_complete': True, 'family_complete': False}))


if __name__ == '__main__':
    main()
