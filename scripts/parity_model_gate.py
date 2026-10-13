# SPDX-License-Identifier: Apache-2.0
"""Compare retained KiCad model facts with a source-bound native pcbnew read."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def validate_model_gate(payload: dict, native: dict) -> None:
    digest = payload.get('report', {}).get('source_sha256')
    if (native.get('contract') != 'spike/native-kicad-model-facts/v1'
            or native.get('source_sha256') != digest or not native.get('kicad_version')):
        raise ValueError('Native model evidence source/contract mismatch.')
    design = payload['design']
    expected = native.get('models')
    if not isinstance(expected, list) or not expected or len(expected) != len(design['models']):
        raise ValueError('Native model occurrence coverage differs.')
    components = {c['source_id']: c for c in design['components']}
    seen = set()
    for observed, model in zip(expected, design['models']):
        raw = model['extensions']['spike.v1']
        facts = raw['source_placement']
        owner = components.get(observed['component_source_id'])
        if (owner is None or model['id'] not in owner['model_ids'] or model['id'] in seen
                or raw['component'] != observed['component_source_id']
                or model['uri'] != observed['uri'] or facts['ordinal'] != observed['ordinal']
                or facts['declared_vectors'] != observed['vectors']
                or facts['valid_source_vectors'] is not True
                or facts['semantic_state'] != 'source_placement_unapplied'
                or facts['projection'] != 'forbidden' or model['transform'] != []):
            raise ValueError('Retained model facts differ from native source or claim projection.')
        seen.add(model['id'])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--import-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import pcbnew  # Native KiCad Python only; not a SPIKE runtime dependency.
    board = pcbnew.LoadBoard(str(args.source.resolve()))
    models = []
    for footprint in board.GetFootprints():
        for ordinal, model in enumerate(footprint.Models()):
            models.append({'component_source_id': footprint.m_Uuid.AsString(), 'ordinal': ordinal,
                           'uri': model.m_Filename,
                           'vectors': {key: [v.x, v.y, v.z] for key, v in
                                       [('offset', model.m_Offset), ('scale', model.m_Scale), ('rotate', model.m_Rotation)]}})
    native = {'contract': 'spike/native-kicad-model-facts/v1',
              'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
              'kicad_version': pcbnew.GetBuildVersion(), 'models': models}
    validate_model_gate(json.loads(args.import_file.read_text(encoding='utf-8')), native)
    args.output.write_text(json.dumps(native, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'Native model facts passed: {len(models)} occurrences; no solid/placement qualification.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
