from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.component_catalog import catalog
from spikes_studio.library_pins import pin_contract,preview_height


class LibraryPins(unittest.TestCase):
    def test_every_digital_preset_has_named_numbered_power_and_io(self):
        count=0
        for record in catalog()['records']:
            contract=pin_contract(record)
            if record['category']=='Digital':
                self.assertIsNotNone(contract);count+=1
            if contract:
                pins=contract['pins']
                self.assertEqual(len(pins),len({p['number'] for p in pins}))
                self.assertEqual(len(pins),len({p['name'] for p in pins}))
                self.assertIn('power',{p['role'] for p in pins})
                self.assertIn('output',{p['role'] for p in pins})
                self.assertGreaterEqual(preview_height(record),240)
                self.assertEqual(contract['execution'],'equation_bench_only')
        self.assertEqual(count,500)

    def test_adc_has_individual_bits_and_isolation_keeps_grounds_separate(self):
        records=catalog()['records']
        adc=next(r for r in records if r['family']=='adc')
        names=[p['name'] for p in pin_contract(adc)['pins']]
        self.assertEqual(len([n for n in names if n.startswith('D') and n[1:].isdigit()]),adc['parameters']['bits'])
        isolation=next(r for r in records if r['family']=='isolation_amplifier')
        names=[p['name'] for p in pin_contract(isolation)['pins']]
        self.assertTrue({'VDD1','GND1','VDD2','GND2'}<=set(names))
