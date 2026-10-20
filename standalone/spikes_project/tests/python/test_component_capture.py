# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'studio/python'))

from spikes_studio.component_capture import capture_selection, capture_subsheet
from spikes_studio.document import Document
from spikes_studio.part_properties import parse

ROOT = Path(__file__).resolve().parents[4]
NATIVE_LIBRARY = Path(os.environ.get(
    'SPIKES_TEST_NATIVE_LIBRARY', ROOT / 'build-spikes-current-vs18-20260906/Release/spikes_c_api.dll'))


class ComponentCaptureTests(unittest.TestCase):
    def test_rc_capture_is_analytically_equivalent_and_keeps_internal_net_private(self):
        document = Document.from_netlist(
            'RC filter\nV1 input 0 1\nR1 input output 2k\nC1 output 0 5u\n.op\n.end\n')
        parts = {part['ref']: part for part in document.data['components']}
        before = deepcopy(document.data)
        result = capture_selection(document, [parts['R1']['id'], parts['C1']['id']], 'RC_CELL')
        self.assertEqual(result['pins'], ['INPUT', 'GND'])
        self.assertIn('.subckt RC_CELL INPUT GND', result['source'])
        self.assertNotIn(' output ', result['source'].splitlines()[0])
        project = parse('Captured RC\n' + result['source'] +
                        'V1 source 0 1\nX1 source 0 RC_CELL\n.op\n.end\n')
        resistor = next(item for item in project.elements if item.name == 'X1:R1')
        capacitor = next(item for item in project.elements if item.name == 'X1:C1')
        self.assertAlmostEqual(resistor.value * capacitor.value, .01)
        self.assertEqual(resistor.negative_node, capacitor.positive_node)
        self.assertTrue(resistor.negative_node.startswith('x1:'))
        self.assertEqual(capacitor.negative_node, '0')
        self.assertEqual(document.data, before)

    def test_ports_are_crossing_nets_plus_explicit_ground_in_source_order(self):
        document = Document.from_netlist(
            'Topology\nV1 drive 0 1\nR1 drive private 1k\nR2 private sense 2k\n'
            'R3 sense 0 3k\nR4 sense load 4k\nR5 load 0 5k\n.op\n.end\n')
        parts = {part['ref']: part for part in document.data['components']}
        result = capture_selection(document, [parts['R1']['id'], parts['R2']['id'], parts['R3']['id']], 'DIVIDER')
        self.assertEqual(result['pins'], ['DRIVE', 'SENSE', 'GND'])
        self.assertIn('R1 DRIVE private 1k', result['source'])
        self.assertIn('R2 private SENSE 2k', result['source'])
        self.assertIn('R3 SENSE GND 3k', result['source'])

    def test_reference_ground_keeps_gnd_pin_when_an_internal_net_has_that_name(self):
        document = Document.from_netlist(
            'Ground names\nV1 input 0 1\nR1 input gnd 1k\nR2 gnd 0 2k\n.op\n.end\n')
        parts = {part['ref']: part for part in document.data['components']}
        result = capture_selection(document, [parts['R1']['id'], parts['R2']['id']], 'GROUND_SAFE')
        self.assertEqual(result['pins'], ['INPUT', 'GND'])
        self.assertIn('R1 INPUT _CAP_gnd 1k', result['source'])
        self.assertIn('R2 _CAP_gnd GND 2k', result['source'])

    def test_parameters_models_and_external_source_commands_fail_closed(self):
        document = Document.from_netlist(
            'Model dependency\n.param rv=2k\nV1 in 0 1\nD1 in out DM\nR1 out 0 {rv}\n'
            '.model DM D(IS=2p N=1.2)\n.op\n.end\n')
        parts = {part['ref']: part for part in document.data['components']}
        result = capture_selection(document, [parts['D1']['id'], parts['R1']['id']], 'MODELED')
        self.assertIn('.param rv=2k', result['source'])
        self.assertIn('.model DM D(IS=2p N=1.2)', result['source'])
        self.assertIn('R1 out GND {rv}', result['source'])

        document.data['source'] = '.include vendor.lib\n' + document.data['source']
        with self.assertRaisesRegex(ValueError, 'nonportable'):
            capture_selection(document, [parts['D1']['id']], 'BAD')

    def test_current_controlled_source_requires_and_keeps_its_branch_dependency(self):
        document = Document.from_netlist(
            'Controlled\nV1 control 0 1\nF1 0 output V1 2\nR1 output 0 1k\n.op\n.end\n')
        parts = {part['ref']: part for part in document.data['components']}
        before = deepcopy(document.data)
        with self.assertRaisesRegex(ValueError, 'omitted control branch'):
            capture_selection(document, [parts['F1']['id']], 'CONTROLLED')
        result = capture_selection(document, [parts['V1']['id'], parts['F1']['id']], 'CONTROLLED')
        self.assertIn('F1 GND OUTPUT V1 2', result['source'])
        self.assertIn('V1 control GND 1', result['source'])
        self.assertEqual(document.data, before)

    def test_subsheet_reuses_dependencies_and_specializes_top_instance_parameters(self):
        document = Document.from_netlist(
            'Hierarchy\n.param base=1k\n'
            '.subckt leaf p n params: scale=1\nR1 p n {scale}\n.ends leaf\n'
            '.subckt cell input output params: resistance={base}\n'
            'XLEAF input middle leaf scale={resistance}\nR2 middle output {resistance}\n.ends cell\n'
            'V1 in 0 1\nXTOP in 0 cell resistance=2k\n.op\n.end\n')
        before = deepcopy(document.data)
        result = capture_subsheet(document, 'XTOP', 'CAPTURED_CELL')
        self.assertEqual(result['pins'], ['input', 'output'])
        self.assertIn('.subckt leaf p n params: scale=1', result['source'])
        self.assertIn('.subckt CAPTURED_CELL input output params: resistance=2k', result['source'])
        project = parse('Captured hierarchy\n' + result['source'] +
                        'V1 in 0 1\nX1 in 0 CAPTURED_CELL\n.op\n.end\n')
        self.assertEqual({item.value for item in project.elements if item.kind == 'resistor'}, {2000.0})
        self.assertEqual(document.data, before)
        self.assertEqual(result['origin']['scope_path'], 'XTOP')

    def test_selection_inside_one_hierarchy_scope_uses_instance_net_identity(self):
        document = Document.from_netlist(
            'Scoped selection\n.subckt cell input ref\nR1 input middle 3k\nC1 middle ref 2u\n.ends cell\n'
            'V1 source 0 1\nX1 source 0 cell\n.op\n.end\n')
        parts = {part['ref']: part for part in document.data['components']}
        result = capture_selection(document, [parts['X1:R1']['id'], parts['X1:C1']['id']], 'SCOPED_RC')
        self.assertEqual(result['pins'], ['INPUT', 'GND'])
        self.assertIn('R1 INPUT middle 3k', result['source'])
        self.assertIn('C1 middle GND 2u', result['source'])
        project = parse('Scoped captured\n' + result['source'] +
                        'V1 in 0 1\nXNEW in 0 SCOPED_RC\n.op\n.end\n')
        self.assertEqual({item.name for item in project.elements}, {'V1', 'XNEW:R1', 'XNEW:C1'})

    def test_hierarchy_selection_rejects_conflicting_definition_and_instance_parameters(self):
        document = Document.from_netlist(
            'Scoped parameters\n.param r=9k c=9u\n'
            '.subckt cell input ref params: r=1k c=1u\n'
            'R1 input middle {r}\nC1 middle ref {c}\n.ends cell\n'
            'V1 source 0 1\nX1 source 0 cell r=2k c=2u\n.op\n.end\n')
        parts = {part['ref']: part for part in document.data['components']}
        parsed = parse(document.data['source'])
        self.assertEqual(next(item.value for item in parsed.elements if item.name == 'X1:R1'), 2000.0)
        before = deepcopy(document.data)
        with self.assertRaisesRegex(ValueError, 'Parameterized hierarchy selection'):
            capture_selection(document, [parts['X1:R1']['id'], parts['X1:C1']['id']], 'WRONG_IF_REBOUND')
        self.assertEqual(document.data, before)

    def test_subsheet_rejects_nested_override_and_global_dependency(self):
        nested = Document.from_netlist(
            'Nested\n.subckt leaf a b params: r=1k\nR1 a b {r}\n.ends leaf\n'
            '.subckt parent a b params: r=2k\nXCHILD a b leaf r={r}\n.ends parent\n'
            'V1 in 0 1\nXTOP in 0 parent r=3k\n.op\n.end\n')
        with self.assertRaisesRegex(ValueError, 'ancestor-local'):
            capture_subsheet(nested, 'XTOP:XCHILD', 'CHILD_COPY')

        global_source = Document.from_netlist(
            'Global\n.global supply\n.subckt cell a b\nR1 a supply 1k\nR2 supply b 1k\n.ends cell\n'
            'V1 in 0 1\nX1 in 0 cell\n.op\n.end\n')
        with self.assertRaisesRegex(ValueError, 'global node'):
            capture_subsheet(global_source, 'X1', 'GLOBAL_COPY')

    def test_nested_subsheet_rejects_implicit_ancestor_parameter_rebinding(self):
        document = Document.from_netlist(
            'Inherited context\n.param inherited=9k\n'
            '.subckt leaf a b params: r={inherited}\nR1 a b {r}\n.ends leaf\n'
            '.subckt parent a b params: inherited=2k\nXCHILD a b leaf\n.ends parent\n'
            'V1 in 0 1\nXTOP in 0 parent\n.op\n.end\n')
        original = parse(document.data['source'])
        self.assertEqual(next(item.value for item in original.elements
                              if item.name == 'XTOP:XCHILD:R1'), 2000.0)
        rebound = parse(
            'Unsafe copied child\n.param inherited=9k\n'
            '.subckt copy a b params: r={inherited}\nR1 a b {r}\n.ends copy\n'
            'V1 in 0 1\nX1 in 0 copy\n.op\n.end\n')
        self.assertEqual(next(item.value for item in rebound.elements if item.name == 'X1:R1'), 9000.0)
        before = deepcopy(document.data)
        with self.assertRaisesRegex(ValueError, 'ancestor-local'):
            capture_subsheet(document, 'XTOP:XCHILD', 'SAFE_CHILD')
        self.assertEqual(document.data, before)

    def test_subsheet_name_cannot_shadow_a_retained_dependency(self):
        document = Document.from_netlist(
            'Names\n.subckt leaf a b\nR1 a b 1k\n.ends leaf\n'
            '.subckt parent a b\nX1 a b leaf\n.ends parent\n'
            'V1 in 0 1\nXTOP in 0 parent\n.op\n.end\n')
        with self.assertRaisesRegex(ValueError, 'collides with retained dependency'):
            capture_subsheet(document, 'XTOP', 'leaf')

    @unittest.skipUnless(NATIVE_LIBRARY.is_file(), 'Native library required')
    def test_native_transient_matches_original_rc_when_library_is_available(self):
        from spikes_studio.run_control import native_batch
        original = ('Original\nV1 input 0 PULSE(0 1 0 1u 1u 10m 20m)\n'
                    'R1 input output 2k\nC1 output 0 5u\n.tran 100u 2m uic\n.end\n')
        document = Document.from_netlist(original)
        parts = {part['ref']: part for part in document.data['components']}
        captured = capture_selection(document, [parts['R1']['id'], parts['C1']['id']], 'RC_CELL')
        replacement = ('Captured\n' + captured['source'] +
                       'V1 input 0 PULSE(0 1 0 1u 1u 10m 20m)\n'
                       'X1 input 0 RC_CELL\n.tran 100u 2m uic\n.end\n')
        first = native_batch(original, str(NATIVE_LIBRARY))
        second = native_batch(replacement, str(NATIVE_LIBRARY))
        self.assertEqual(first['data']['time_s'], second['data']['time_s'])
        self.assertEqual(first['data']['node_voltage_v']['output'],
                         second['data']['node_voltage_v']['x1:output'])


if __name__ == '__main__':
    unittest.main()
