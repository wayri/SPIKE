# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'studio/python'))

from spikes_studio.document import Document
from spikes_studio.schematic_clipboard import (
    CONTRACT, copy_fragment, place, prepare_paste, preview, rotate_plan,
)


DECK = """Clipboard test
V1 supply 0 5
R1 supply shared 1k
R2 shared 0 2k
.op
.end
"""


class SchematicClipboardTests(unittest.TestCase):
    def connected_document(self):
        document = Document.from_netlist(DECK)
        parts = {part['ref']: part for part in document.data['components']}
        document.connect((parts['R1']['id'], 1), (parts['R2']['id'], 0), [[330, 210]])
        return document, parts

    def test_copy_paste_isolates_external_nets_and_preserves_internal_wiring(self):
        document, parts = self.connected_document()
        policy={'tier':'ideal','enforce':False,'required_parasitics':[],
                'parasitic_values':{}}
        document.commit(lambda data:data['model_policy']['components'].update(R1=policy))
        payload = copy_fragment(document, [parts['R1']['id'], parts['R2']['id']])
        self.assertEqual(json.loads(json.dumps(payload))['contract'], CONTRACT)
        plan = prepare_paste(document, payload)
        pasted_ids = place(document, plan, (600, 400))
        pasted = [part for part in document.data['components'] if part['id'] in pasted_ids]
        self.assertEqual([part['ref'] for part in pasted], ['R3', 'R4'])
        self.assertEqual(pasted[0]['nodes'][1], pasted[1]['nodes'][0])
        self.assertNotEqual(pasted[0]['nodes'][0].casefold(), 'supply')
        self.assertEqual(pasted[1]['nodes'][1], '0')
        self.assertEqual(len(document.data['wires']), 2)
        copied_wire = document.data['wires'][-1]
        self.assertEqual({copied_wire['a'][0], copied_wire['b'][0]}, set(pasted_ids))
        self.assertEqual(copied_wire['waypoints'], [[490.0, 430.0]])
        self.assertIn('R3 ', document.data['source'])
        self.assertIn('R4 ', document.data['source'])
        self.assertEqual(document.data['model_policy']['components']['R3'],policy)
        Document(document.data).validate()

    def test_preview_rotation_and_escape_style_cancellation_do_not_mutate_document(self):
        document, parts = self.connected_document()
        before = deepcopy(document.data)
        undo_count = len(document.undo_stack)
        payload = copy_fragment(document, [parts['R1']['id'], parts['R2']['id']])
        plan = prepare_paste(document, payload)
        initial, _ = preview(plan, (500, 300))
        initial_bend = plan['wires'][0]['bend']
        rotate_plan(plan)
        rotated, _ = preview(plan, (500, 300))
        self.assertEqual(plan['quarter_turns'], 1)
        self.assertNotEqual(plan['wires'][0]['bend'], initial_bend)
        self.assertEqual(rotated[0]['rotation'], (initial[0]['rotation'] + 90) % 360)
        self.assertEqual(document.data, before)
        self.assertEqual(len(document.undo_stack), undo_count)

    def test_paste_is_one_undo_transaction_and_validation_failure_rolls_back(self):
        document, parts = self.connected_document()
        payload = copy_fragment(document, [parts['R1']['id'], parts['R2']['id']])
        plan = prepare_paste(document, payload)
        before = deepcopy(document.data)
        place(document, plan, (450, 350))
        self.assertEqual(len(document.undo_stack), 2)
        document.undo()
        self.assertEqual(document.data, before)

        bad = prepare_paste(document, payload)
        bad['wires'][0]['b'] = list(bad['wires'][0]['a'])
        before = deepcopy(document.data)
        undo_count = len(document.undo_stack)
        with self.assertRaisesRegex(ValueError, 'endpoints must differ'):
            place(document, bad, (450, 350))
        self.assertEqual(document.data, before)
        self.assertEqual(len(document.undo_stack), undo_count)

    def test_fragment_rejects_hierarchical_or_stale_selection(self):
        document, parts = self.connected_document()
        with self.assertRaisesRegex(ValueError, 'existing components'):
            copy_fragment(document, ['missing'])
        next(part for part in document.data['components'] if part['id'] == parts['R1']['id'])['ref'] = 'X1:R1'
        with self.assertRaisesRegex(ValueError, 'top-level'):
            copy_fragment(document, [parts['R1']['id']])

    def test_dependent_expressions_and_record_injection_fail_before_mutation(self):
        behavioral=Document.from_netlist('Behavioral\nV1 in 0 1\nB1 out 0 V=V(in)*2\nR1 out 0 1k\n.op\n.end\n')
        part=next(part for part in behavioral.data['components'] if part['ref']=='B1')
        payload=copy_fragment(behavioral,[part['id']]);before=deepcopy(behavioral.data)
        with self.assertRaisesRegex(ValueError,'dependent source semantics'):
            prepare_paste(behavioral,payload)
        self.assertEqual(behavioral.data,before)

        document,parts=self.connected_document();payload=copy_fragment(document,[parts['R1']['id']])
        payload['components'][0]['record']+='R99 injected 0 1k\n'
        before=deepcopy(document.data)
        with self.assertRaisesRegex(ValueError,'exactly its declared instance'):
            prepare_paste(document,payload)
        self.assertEqual(document.data,before)

    def test_prepare_preserves_existing_source_bytes_and_declares_only_copied_instances(self):
        source='Byte preserve\r\n* keep this comment exactly\r\nR1 a b 1k\r\nR2 b 0 2k\r\n.op\r\n.end\r\n'
        document=Document.from_netlist(source);parts={part['ref']:part for part in document.data['components']}
        plan=prepare_paste(document,copy_fragment(document,[parts['R1']['id']]))
        end=source.lower().index('.end')
        self.assertTrue(plan['source'].startswith(source[:end]))
        self.assertTrue(plan['source'].endswith(source[end:]))
        parsed=Document.from_netlist(plan['source'])
        self.assertEqual([part['ref'] for part in parsed.data['components']],['R1','R2','R3'])

    def test_cross_document_paste_rejects_ambient_parameter_or_model_rebinding(self):
        source=Document.from_netlist('Source\n.param RV=1k\nR1 a 0 {RV}\n.op\n.end\n')
        payload=copy_fragment(source,[source.data['components'][0]['id']])
        destination=Document.from_netlist('Destination\n.param RV=2k\nV1 a 0 1\n.op\n.end\n')
        before=deepcopy(destination.data)
        with self.assertRaisesRegex(ValueError,'source sheet'):
            prepare_paste(destination,payload)
        self.assertEqual(destination.data,before)

        source.apply_source(source.data['source'].replace('RV=1k','RV=3k'))
        with self.assertRaisesRegex(ValueError,'changed since copy'):
            prepare_paste(source,payload)

    def test_forged_visual_semantics_and_junction_routes_fail_closed(self):
        document,parts=self.connected_document();payload=copy_fragment(document,[parts['R1']['id']])
        payload['components'][0]['visual']['value']='999meg'
        with self.assertRaisesRegex(ValueError,'geometry'):
            prepare_paste(document,payload)

        document=Document.from_netlist('Junction\nR1 common 0 1k\nR2 common 0 2k\n.op\n.end\n')
        parts={part['ref']:part for part in document.data['components']};junction='j'
        document.data['junctions']=[{'id':junction,'x':300,'y':200,
            'source_terminal':[parts['R1']['id'],0],'source_node':'common'}]
        document.data['wires']=[
            {'id':'w1','a':[parts['R1']['id'],0],'b':[junction],'waypoints':[],'bend':'horizontal','manual':True},
            {'id':'w2','a':[junction],'b':[parts['R2']['id'],0],'waypoints':[],'bend':'horizontal','manual':True},
        ]
        document.validate()
        with self.assertRaisesRegex(ValueError,'explicit junction route'):
            copy_fragment(document,[parts['R1']['id'],parts['R2']['id']])


if __name__ == '__main__':
    unittest.main()
