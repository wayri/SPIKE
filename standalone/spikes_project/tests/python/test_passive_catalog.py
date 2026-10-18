# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.passive_catalog import SERIES,PACKAGES,TOLERANCES,preferred_values,nearest,make_record,model
from spikes_studio.component_catalog import catalog,native_recipe,validate_record
from spikes_studio.document import Document
from spikes_studio.library_browser import insertion_plan,apply_insertion,CatalogIndex


class PassiveCatalogTests(unittest.TestCase):
    def test_preferred_tables_and_range(self):
        for name,count in [('E3',3),('E6',6),('E12',12),('E24',24),('E48',48),('E96',96),('E192',192)]:
            self.assertEqual(len(SERIES[name]),count)
        self.assertIn(920,SERIES['E192']);self.assertNotIn(919,SERIES['E192'])
        values=preferred_values('E192',.001,1e9);self.assertEqual(len(values),2305)
        self.assertEqual((values[0],values[-1]),(.001,1e9))
        self.assertEqual(nearest(105,'E24')['value'],100)
        self.assertEqual(nearest(1234,'E192')['value'],1230)
        self.assertEqual(nearest(1234,'E96')['value'],1240)
        with self.assertRaises(ValueError):preferred_values('E192',1e-30,1e30)

    def test_all_packages_tolerances_and_custom_values_are_generic(self):
        for package in PACKAGES:
            for tolerance in TOLERANCES:
                record=make_record('resistor',1.234567,package=package,tolerance_percent=tolerance,construction='Thin film')
                validate_record(record);self.assertIsNone(record['manufacturer'])
                self.assertEqual(record['parameters']['r'],1.234567)
        with self.assertRaises(ValueError):make_record('resistor',1,package='claimed-vendor-package')

    def test_extended_catalog_and_every_recipe_parse(self):
        from python.spikes.netlist import parse_netlist
        payload=catalog(include_passives=True);self.assertEqual(len(payload['records']),7908)
        self.assertEqual(len(catalog()['records']),5000) # Legacy API grid remains compatible.
        rows=CatalogIndex(payload['records']).query('id:standard.')
        self.assertEqual(len(rows),2908)
        for record in rows:
            recipe=native_recipe(record);pins=['in','0'] if len(recipe['pins'])==2 else ['in','0','sense_p','sense_n']
            source='Passive parse\nV1 supply 0 1\nRS supply in 1\n'+recipe['source']+'X1 '+' '.join(pins)+' '+recipe['name']+'\n.op\n.end\n'
            self.assertTrue(parse_netlist(source,native_extensions=True).elements)

    def test_parasitics_and_provenance_survive_insert_save_reopen(self):
        record=make_record('capacitor',1e-6,package='2512',series_resistance_ohm=.1,series_inductance_h=2e-9,leakage_resistance_ohm=1e8)
        doc=Document.from_netlist('Insert\nV1 in 0 1\nR1 in out 1k\n.op\n.end\n')
        plan=insertion_plan(doc,record,{'P':'out','N':'0'},primitive=True)
        self.assertIn('RSER',plan['source']);self.assertIn('LSER',plan['source']);apply_insertion(doc,plan,record['id'])
        saved=doc.data['metadata']['passive_models'][plan['model']]['record'];self.assertEqual(saved['package_code'],'2512')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'model.spksch';doc.save(path);self.assertEqual(Document.load(path).data['metadata']['passive_models'],doc.data['metadata']['passive_models'])
        doc.undo();self.assertNotIn('passive_models',doc.data['metadata'])

    def test_kelvin_contact_model_and_explicit_temp_corner(self):
        shunt=model(make_record('kelvin_shunt',.001,contact_resistance_ohm=.0001));self.assertEqual(shunt['pins'],['FP','FN','SP','SN'])
        spec=model(make_record('resistor',100,tc1_per_k=50e-6,temperature_c=125,tolerance_percent=.05,corner=1))
        self.assertAlmostEqual(spec['effective_value'],100*(1+.0005)*(1+.005))

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_LIBRARY'),'Native DLL required')
    def test_every_preferred_template_executes_with_native_dc_oracle(self):
        from python.spikes.netlist import parse_netlist
        from python.spikes.native_runner import run_native_project
        for record in catalog(include_passives=True)['records'][5000:]:
            recipe=native_recipe(record);pins=['in','0'] if len(recipe['pins'])==2 else ['in','0','sense_p','sense_n']
            source='Passive native oracle\nV1 supply 0 1\nRS supply in 1\n'+recipe['source']+'X1 '+' '.join(pins)+' '+recipe['name']+'\n.op\n.end\n'
            result=run_native_project(parse_netlist(source,native_extensions=True),os.environ['SPIKES_TEST_LIBRARY']).to_dict()
            self.assertEqual(result['status'],'completed',record['id'])
            data=result['data'];kind=record['passive_kind']
            expected=1. if kind=='capacitor' else 0. if kind=='inductor' else recipe['effective_value']/(1+recipe['effective_value'])
            self.assertAlmostEqual(data['node_voltage_v']['in'],expected,delta=1e-9,msg=record['id'])


if __name__=='__main__':unittest.main()
