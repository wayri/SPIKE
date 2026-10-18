# SPDX-License-Identifier: Apache-2.0
"""The shipped catalog schema tag and API contract tag must agree."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.manufacturer_discovery import CONTRACT,load_catalog,validate


class DiscoveryContractAliasTests(unittest.TestCase):
    def test_shipped_schema_tag_loads(self):
        self.assertTrue(load_catalog()['records'])
        for tags in ({'schema':CONTRACT},{'contract':CONTRACT},{'schema':CONTRACT,'contract':CONTRACT}):
            self.assertEqual(validate(dict(tags,records=[]))['records'],[])

    def test_missing_or_conflicting_tags_are_rejected(self):
        for tags in ({},{'schema':'unknown'},{'schema':CONTRACT,'contract':'unknown'}):
            with self.assertRaises(ValueError):validate(dict(tags,records=[]))
