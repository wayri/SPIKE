# SPDX-License-Identifier: Apache-2.0
"""Public schema and real top-level worker dispatch, including failed requests."""
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator

from python.spike_core.service import handle
from tests.python.test_assembly_thermomechanical import request

ROOT = Path(__file__).resolve().parents[2]


class StructuralContractTests(unittest.TestCase):
    def test_public_schemas_and_actual_top_level_worker(self):
        for stem in ('assembly-tetra-structural', 'assembly-thermomechanical'):
            raw = request()
            if stem == 'assembly-tetra-structural': raw = raw['structural']
            validators = [Draft202012Validator(json.loads((ROOT/'schemas'/f'{stem}-{kind}-v1.schema.json').read_text(encoding='utf-8')))
                          for kind in ('request', 'result')]
            for validator in validators: validator.check_schema(validator.schema)
            validators[0].validate(raw)
            out = handle({'method': 'run_'+stem.replace('-', '_'), 'params': {'request': raw}})
            self.assertTrue(out['ok'], out)
            validators[1].validate(out['result'])

    def test_worker_bad_material_unknown_parameter_and_mesh_rejected(self):
        for mutation in ('material', 'mesh', 'override'):
            raw = request(); params = {'request': raw}
            if mutation == 'material': raw['structural']['materials'][0]['poisson_ratio'] = .5
            if mutation == 'mesh': raw['structural']['mesh']['vertices'][0][0] = .01
            if mutation == 'override': params['executable'] = 'anything'
            out = handle({'method': 'run_assembly_thermomechanical', 'params': params})
            self.assertFalse(out['ok'])
            self.assertNotIn('result', out)
