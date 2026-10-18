# SPDX-License-Identifier: Apache-2.0
import unittest

from spikes_studio.schematic_symbol_renderer import label_positions


class SchematicSymbolRendererTests(unittest.TestCase):
    def test_rotated_identity_stack_stays_upright_and_clear_of_body(self):
        base=dict(x=100,y=200)
        self.assertEqual(label_positions(base|dict(rotation=0)),((72,157),(72,224),(72,244)))
        rotated=label_positions(base|dict(rotation=90))
        self.assertEqual(rotated,((134,164),(134,184),(134,204)))
        self.assertEqual(label_positions(base|dict(rotation=270)),rotated)


if __name__=='__main__':unittest.main()
