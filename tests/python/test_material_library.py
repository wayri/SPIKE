# SPDX-License-Identifier: Apache-2.0
"""Evidence retention and fail-closed scalar admission; no physics qualification."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from python.spike_core.material_library import (
    MaterialError, load_catalog, material_digest, material_snapshot,
    project_scalar_properties, validate_material, validate_snapshot,
)


class MaterialLibraryTests(unittest.TestCase):
    def setUp(self):
        self.records = load_catalog()
        self.copper = deepcopy(self.records[0])

    def test_catalog_coverage_and_status(self):
        self.assertGreaterEqual(len(self.records), 50)
        families = {r['family'] for r in self.records}
        self.assertTrue({'metal', 'ceramic', 'polymer', 'rf-laminate', 'pcb-laminate',
                         'metal-clad', 'flex-laminate', 'conductor'} <= families)
        self.assertTrue(all(p['status'] in {'estimate', 'unavailable', 'manufacturer'}
                            for r in self.records for p in r['properties'].values()))

    def test_primary_rf_record_retains_conditions_and_axes(self):
        ro = next(r for r in self.records if r['id'] == 'rogers-ro4350b')
        self.assertEqual(ro['properties']['density']['value'], 1860)
        self.assertEqual(ro['properties']['thermal_conductivity']['applicability']['temperature_k'], [353.15, 353.15])
        self.assertEqual(ro['properties']['thermal_expansion']['values'], [10e-6,12e-6,32e-6])
        self.assertEqual(ro['properties']['relative_permittivity']['samples'][0]['frequency_hz'], 1e10)
        with self.assertRaises(MaterialError):
            project_scalar_properties(ro, ['relative_permittivity'])

    def test_detached_snapshot_and_digest_roundtrip(self):
        saved = material_snapshot(self.copper)
        self.assertEqual(validate_snapshot(json.loads(json.dumps(saved))), saved)
        reordered = dict(reversed(list(self.copper.items())))
        self.assertEqual(material_digest(reordered), saved['digest'])
        self.copper['properties']['density']['value'] = 8000
        self.assertEqual(saved['record']['properties']['density']['value'], 8960)
        self.assertNotEqual(material_digest(self.copper), saved['digest'])
        saved['record']['description'] += ' tampered'
        with self.assertRaises(MaterialError):
            validate_snapshot(saved)

    def test_projection_requires_estimate_acceptance_and_requested_properties(self):
        with self.assertRaises(MaterialError):
            project_scalar_properties(self.copper, ['density'])
        self.assertEqual(project_scalar_properties(self.copper, ['density'], allow_estimates=True), {'density':8960})
        for names in (['relative_permittivity'], ['imaginary'], []):
            with self.assertRaises(MaterialError):
                project_scalar_properties(self.copper, names, allow_estimates=True)

    def test_axes_preserved_and_never_reduced(self):
        prop = self.copper['properties']['thermal_conductivity']
        del prop['value']
        prop.update(shape='orthotropic', axes=['warp', 'fill', 'normal'], values=[1, 2, .3])
        self.assertEqual(validate_material(self.copper), self.copper)
        self.assertEqual(material_snapshot(self.copper)['record']['properties']['thermal_conductivity']['axes'], ['warp', 'fill', 'normal'])
        with self.assertRaises(MaterialError):
            project_scalar_properties(self.copper, ['thermal_conductivity'], allow_estimates=True)
        prop['axes'][1] = 'warp'
        with self.assertRaises(MaterialError):
            validate_material(self.copper)

    def test_samples_preserved_without_interpolation(self):
        prop = self.copper['properties']['thermal_conductivity']
        del prop['value']
        prop['applicability']['temperature_k'] = [293.15, 373.15]
        prop.update(shape='samples', samples=[{'temperature_k':293.15, 'frequency_hz':1e6, 'value':390},
                                             {'temperature_k':373.15, 'frequency_hz':1e6, 'value':380}])
        self.assertEqual(validate_material(self.copper), self.copper)
        with self.assertRaises(MaterialError):
            project_scalar_properties(self.copper, ['thermal_conductivity'], allow_estimates=True)
        prop['samples'][1]['temperature_k'] = 293.15
        with self.assertRaises(MaterialError):
            validate_material(self.copper)

    def test_malformed_and_nonfinite(self):
        for value in (float('nan'), float('inf'), -1, True, '8960'):
            raw = deepcopy(self.copper)
            raw['properties']['density']['value'] = value
            with self.subTest(value=value), self.assertRaises(MaterialError):
                validate_material(raw)
        for value in (-1, .5, 2):
            raw = deepcopy(self.copper)
            raw['properties']['poissons_ratio']['value'] = value
            with self.subTest(nu=value), self.assertRaises(MaterialError):
                validate_material(raw)
        for key, value in [('unit','g/cm^3'), ('status','validated'), ('shape','tensor')]:
            raw = deepcopy(self.copper)
            raw['properties']['density'][key] = value
            with self.subTest(key=key), self.assertRaises(MaterialError):
                validate_material(raw)
        raw = deepcopy(self.copper)
        raw['properties']['density']['applicability']['temperature_k'] = [400, 300]
        with self.assertRaises(MaterialError):
            validate_material(raw)

    def test_catalog_rejects_duplicates_and_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'catalog.json'
            for version, records in [(1, [self.copper, self.copper]), (2,[self.copper]), (True,[self.copper])]:
                path.write_text(json.dumps({'schema_version':version, 'license':'Apache-2.0', 'materials':records}), encoding='utf-8')
                with self.assertRaises(MaterialError):
                    load_catalog(path)


if __name__ == '__main__':
    unittest.main()
