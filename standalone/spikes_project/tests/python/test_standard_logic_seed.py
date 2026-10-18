# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.standard_logic_seed import records
from spikes_studio.manufacturer_parts import load_catalog, validate_record, is_placeable, find_record
from spikes_studio.component_library_choices import matching_parts


class StandardLogicSeedTests(unittest.TestCase):
    def test_records_are_sourced_review_only(self):
        rows=records();self.assertEqual(len(rows),20)
        for row in rows:
            validate_record(row);self.assertFalse(is_placeable(row));self.assertEqual(len(row['pins']),14)
        self.assertEqual(len({r['mpn'] for r in rows}),20)

    def test_default_library_and_selector_include_seed(self):
        payload=load_catalog();row=find_record('SN74HC02N',payload['records'])
        self.assertEqual(row['pins'][0]['name'],'1Y')
        self.assertEqual(len(matching_parts('nor',records=payload['records'])),2)
        self.assertEqual(len({r['id'] for r in payload['records']}),len(payload['records']))


if __name__=='__main__':unittest.main()
