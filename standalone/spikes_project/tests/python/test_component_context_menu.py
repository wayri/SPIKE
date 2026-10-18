# SPDX-License-Identifier: Apache-2.0
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'studio'/'python'))

from spikes_studio.component_panel import context_row


class ComponentContextTargetTests(unittest.TestCase):
    def test_pointer_row_replaces_stale_selection(self):
        converted=[]
        def convert(point):converted.append(point);return (7,11)
        self.assertEqual(context_row((400,300),(-1,-1),5,1,convert,lambda point:(3,0)),3)
        self.assertEqual(converted,[(400,300)])

    def test_keyboard_keeps_focused_row_and_blank_pointer_clears(self):
        unused=lambda point:(_ for _ in ()).throw(AssertionError('pointer lookup not expected'))
        self.assertEqual(context_row((-1,-1),(-1,-1),5,2,unused,unused),2)
        self.assertEqual(context_row((10,10),(-1,-1),5,2,lambda point:point,lambda point:(-1,0)),-1)


if __name__=='__main__':unittest.main()
