# SPDX-License-Identifier: Apache-2.0
"""Native-parser oracles for scope, actual connectivity and atomic editing."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'studio/python'))
from spikes_studio.document import Document, RC_DECK
from spikes_studio import net_labels as labels
from python.spikes.netlist import parse_netlist

HIERARCHY = '''Scoped labels
V1 supply 0 1
.global rail
.subckt cell input output
R1 input inner 1k
R2 inner output 2k
R3 rail output 10k
.ends cell
X1 supply left cell
X2 supply right cell
Rload1 left 0 3k
Rload2 right 0 4k
.op
.end
'''


def pin(doc, ref, index):
    return [next(p['id'] for p in doc.data['components'] if p['ref'].upper() == ref.upper()), index]


def native(doc):
    return parse_netlist(doc.data['source'], native_extensions=True, transient_capture='rolling')


class NetLabelTests(unittest.TestCase):
    def test_same_local_name_in_repeated_definitions_is_not_global(self):
        doc = Document.from_netlist(HIERARCHY)
        a = labels.attach(doc, 'local', 'inner', pin(doc, 'X1:R1', 1))
        b = labels.attach(doc, 'local', 'INNER', pin(doc, 'X2:R1', 1))
        self.assertEqual((a['sheet_path'], b['sheet_path']), ('X1', 'X2'))
        self.assertEqual((a['net'], b['net']), ('x1:inner', 'x2:inner'))
        self.assertEqual(doc.data['source'], HIERARCHY)
        self.assertNotEqual(native(doc).elements[1].negative_node, native(doc).elements[4].negative_node)
        labels.validate(doc.data)

    def test_global_names_share_native_net_across_instances(self):
        doc = Document.from_netlist(HIERARCHY)
        a = labels.attach(doc, 'global', 'rail', pin(doc, 'X1:R3', 0))
        b = labels.attach(doc, 'global', 'rail', pin(doc, 'X2:R3', 0))
        self.assertEqual(a['net'], b['net'])
        self.assertIn('rail', native(doc).global_nodes)
        self.assertEqual(doc.data['source'], HIERARCHY)

    def test_hierarchical_labels_bind_actual_ordered_instance_ports(self):
        doc = Document.from_netlist(HIERARCHY)
        a = labels.attach(doc, 'hierarchical', 'output', pin(doc, 'X1:R2', 1))
        b = labels.attach(doc, 'hierarchical', 'output', pin(doc, 'X2:R2', 1))
        self.assertEqual((a['net'], b['net']), ('left', 'right'))
        self.assertEqual(native(doc).hierarchy[0].nodes, ('supply', 'left'))
        self.assertEqual(doc.data['source'], HIERARCHY)
        with self.assertRaisesRegex(ValueError, 'resolve'):
            labels.attach(doc, 'hierarchical', 'input', pin(doc, 'X1:R2', 1))
        with self.assertRaisesRegex(ValueError, 'declared port'):
            labels.attach(doc, 'hierarchical', 'invented', pin(doc, 'X1:R2', 1))

    def test_nested_scope_uses_full_instance_path(self):
        source = '''Nested labels
.subckt leaf input output
R1 input inner 1k
R2 inner output 1k
.ends leaf
.subckt parent p q
Xchild p q leaf
.ends parent
V1 in 0 1
X1 in 0 parent
X2 in 0 parent
.op
.end
'''
        doc = Document.from_netlist(source)
        a = labels.attach(doc, 'local', 'inner', pin(doc, 'X1:Xchild:R1', 1))
        b = labels.attach(doc, 'local', 'inner', pin(doc, 'X2:Xchild:R1', 1))
        self.assertEqual(a['sheet_path'], 'X1:XCHILD')
        self.assertNotEqual(a['net'], b['net'])
        h = labels.attach(doc, 'hierarchical', 'input', pin(doc, 'X1:Xchild:R1', 0))
        self.assertEqual(h['net'], 'in')

    def test_global_declaration_does_not_get_invented_inside_hierarchy(self):
        doc = Document.from_netlist(HIERARCHY)
        before = deepcopy(doc.data)
        with self.assertRaisesRegex(ValueError, 'Declare .global'):
            labels.attach(doc, 'global', 'inner', pin(doc, 'X1:R1', 1))
        self.assertEqual(doc.data, before)
        self.assertEqual(doc.undo_stack, [])

    def test_local_hierarchy_rename_rejects_shared_definition_edit(self):
        doc = Document.from_netlist(HIERARCHY)
        before = deepcopy(doc.data)
        with self.assertRaisesRegex(ValueError, 'resolve'):
            labels.attach(doc, 'local', 'new', pin(doc, 'X1:R1', 1))
        self.assertEqual(doc.data, before)

    def test_top_level_label_renames_all_pins_and_consumers_atomically(self):
        doc = Document.from_netlist(RC_DECK)
        doc.add_probe('V(in,out)')
        doc.data['expressions'] = ['V (out) * I(R1)', 'V(in,out)']
        before = deepcopy(doc.data)
        label = labels.attach(doc, 'local', 'sense', pin(doc, 'C1', 0))
        self.assertEqual(doc.data['probes'][0]['expression'], 'V(in,sense)')
        self.assertEqual(doc.data['expressions'], ['V(sense) * I(R1)', 'V(in,sense)'])
        by_ref = {p.name: p for p in native(doc).elements}
        self.assertEqual(by_ref['R1'].negative_node, 'sense')
        self.assertEqual(by_ref['C1'].positive_node, 'sense')
        self.assertEqual(doc.data['revision'], before['revision'] + 1)
        doc.undo(); self.assertEqual(doc.data, before)
        doc.redo(); self.assertEqual(doc.data['labels'][0]['id'], label['id'])

    def test_top_level_same_name_actually_merges_nets(self):
        doc = Document.from_netlist('Merge\nV1 in 0 1\nR1 in a 1k\nR2 in b 2k\nR3 a 0 3k\nR4 b 0 4k\n.op\n.end\n')
        labels.attach(doc, 'local', 'sense', pin(doc, 'R1', 1))
        labels.attach(doc, 'local', 'sense', pin(doc, 'R2', 1))
        by_ref = {p.name: p for p in native(doc).elements}
        self.assertEqual(by_ref['R1'].negative_node, by_ref['R2'].negative_node)
        self.assertEqual(by_ref['R3'].positive_node, by_ref['R4'].positive_node)

    def test_top_level_global_is_real_and_removal_does_not_disconnect(self):
        doc = Document.from_netlist(RC_DECK)
        label = labels.attach(doc, 'global', 'out', pin(doc, 'C1', 0))
        self.assertIn('out', native(doc).global_nodes)
        source = doc.data['source']
        labels.remove(doc, label['id'])
        self.assertEqual(doc.data['source'], source)
        self.assertEqual(doc.data['labels'], [])
        doc.undo(); self.assertEqual(doc.data['labels'][0], label)

    def test_root_global_labels_merge_separate_nets_and_migrate_probes(self):
        doc = Document.from_netlist('Global merge\nV1 in 0 1\nR1 in a 1k\nR2 in b 2k\nR3 a 0 3k\nR4 b 0 4k\n.op\n.end\n')
        labels.attach(doc, 'global', 'rail', pin(doc, 'R1', 1))
        doc.add_probe('V(b)')
        labels.attach(doc, 'global', 'rail', pin(doc, 'R2', 1))
        by_ref = {p.name: p for p in native(doc).elements}
        self.assertEqual(by_ref['R1'].negative_node, 'rail')
        self.assertEqual(by_ref['R2'].negative_node, 'rail')
        self.assertEqual(native(doc).global_nodes, ('rail',))
        self.assertEqual(doc.data['source'].count('.global rail'), 1)
        self.assertEqual(doc.data['probes'][0]['expression'], 'V(rail)')
        self.assertEqual(len(doc.data['labels']), 2)
        before = deepcopy(doc.data)
        with self.assertRaisesRegex(ValueError, 'declared-global'):
            labels.attach(doc, 'global', 'newrail', pin(doc, 'R1', 1), doc.data['labels'][0]['id'])
        self.assertEqual(doc.data, before)

    def test_edit_preserves_id_save_reopen_validates_source(self):
        doc = Document.from_netlist(RC_DECK)
        label = labels.attach(doc, 'local', 'out', pin(doc, 'C1', 0))
        edited = labels.attach(doc, 'local', 'renamed', pin(doc, 'C1', 0), label['id'])
        self.assertEqual(edited['id'], label['id'])
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[4] / '.tmp') as directory:
            path = Path(directory) / 'labels.spksch'
            doc.save(path)
            loaded = Document.load(path)
            labels.validate(loaded.data)
            self.assertEqual(loaded.data, doc.data)

    def test_validation_rejects_forged_or_stale_scope_and_name(self):
        doc = Document.from_netlist(HIERARCHY)
        labels.attach(doc, 'local', 'inner', pin(doc, 'X1:R1', 1))
        for key, value in [('sheet_path', 'X2'), ('net', 'x2:inner'), ('name', 'rail'), ('kind', 'fake')]:
            data = deepcopy(doc.data); data['labels'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                labels.validate(data)
        self.assertEqual(len(labels.reconcile(doc.data)), 1)
        data = deepcopy(doc.data); data['labels'][0]['name'] = 'removed'
        self.assertEqual(labels.reconcile(data), [])

    def test_node_directive_rewrite_and_ground_rename_are_atomic_errors(self):
        doc = Document.from_netlist(RC_DECK.replace('.tran', '.ic V(out)=0\n.tran'))
        before = deepcopy(doc.data)
        with self.assertRaisesRegex(ValueError, 'directives'):
            labels.attach(doc, 'local', 'new', pin(doc, 'C1', 0))
        self.assertEqual(doc.data, before)
        doc = Document.from_netlist(RC_DECK)
        with self.assertRaisesRegex(ValueError, 'cannot be renamed'):
            labels.attach(doc, 'local', 'ground', pin(doc, 'C1', 1))

    def test_wire_label_binds_source_terminal_and_real_route(self):
        doc = Document.from_netlist(RC_DECK)
        doc.connect(pin(doc, 'R1', 1), pin(doc, 'C1', 0))
        ident = doc.data['wires'][0]['id']
        item = labels.attach(doc, 'local', 'out', dict(part_id=pin(doc, 'R1', 1)[0], pin_index=1, wire_id=ident))
        self.assertEqual(item['wire_id'], ident)
        labels.validate(doc.data)
        bad = deepcopy(doc.data); bad['wires'] = []
        self.assertEqual(labels.reconcile(bad), [])

    def test_unknown_label_and_duplicate_terminal_are_errors(self):
        doc = Document.from_netlist(RC_DECK)
        labels.attach(doc, 'local', 'out', pin(doc, 'C1', 0))
        before = deepcopy(doc.data)
        with self.assertRaisesRegex(ValueError, 'already has'):
            labels.attach(doc, 'local', 'out', pin(doc, 'C1', 0))
        with self.assertRaisesRegex(ValueError, 'no longer exists'):
            labels.remove(doc, 'missing')
        self.assertEqual(doc.data, before)

    def test_known_instrument_dashboard_and_wire_references_migrate(self):
        from spikes_studio.plot_workspace import add_attached_plot
        from spikes_studio.dashboard import widget
        doc = Document.from_netlist(RC_DECK)
        endpoint = pin(doc, 'C1', 0)
        add_attached_plot(doc, endpoint[0], endpoint[1], [500, 300])
        doc.connect(pin(doc, 'R1', 1), endpoint)
        doc.data['wires'][0]['parasitics'] = dict(enabled=False, reference='out')
        doc.data['dashboard']['widgets'].append(widget('Meter', 'V(out,0)'))
        labels.attach(doc, 'local', 'sense', endpoint)
        self.assertEqual(doc.data['instruments'][0]['expression'], 'V(sense)')
        self.assertEqual(doc.data['instruments'][0]['anchor'], endpoint[0])
        self.assertEqual(doc.data['dashboard']['widgets'][0]['expression'], 'V(sense,0)')
        self.assertEqual(doc.data['wires'][0]['parasitics']['reference'], 'sense')

    def test_malformed_names_and_stale_source_cannot_rewrite(self):
        doc = Document.from_netlist(RC_DECK)
        for name in ('', 'x:y', 'two words', '.end\n', 'x' * 129):
            before = deepcopy(doc.data)
            with self.subTest(name=name), self.assertRaises(ValueError):
                labels.attach(doc, 'local', name, pin(doc, 'C1', 0))
            self.assertEqual(doc.data, before)
        doc.data['components'][1]['nodes'][1] = 'forged'
        before = deepcopy(doc.data)
        with self.assertRaisesRegex(ValueError, 'disagree'):
            labels.attach(doc, 'local', 'sense', pin(doc, 'C1', 0))
        self.assertEqual(doc.data, before)

    def test_failed_short_circuit_merge_leaves_source_labels_and_undo(self):
        doc = Document.from_netlist(RC_DECK)
        before = deepcopy(doc.data)
        with self.assertRaises(ValueError):
            labels.attach(doc, 'local', 'in', pin(doc, 'R1', 1))
        self.assertEqual(doc.data, before)
        self.assertEqual(doc.undo_stack, [])


if __name__ == '__main__':
    unittest.main()
