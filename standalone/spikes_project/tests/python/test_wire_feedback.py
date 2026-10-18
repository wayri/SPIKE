# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import os
import unittest
from spikes_studio.document import Document,RC_DECK
from spikes_studio.schematic_layout import startup_layout
from spikes_studio.wire_models import lower,extraction_request,import_extraction
from spikes_studio.schematic_feedback import badge


class WireFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.document=Document.from_netlist(RC_DECK);startup_layout(self.document)
        self.wire=self.document.data['wires'][0]
        self.model=dict(enabled=True,r_ohm=2.,l_h=1e-6,c_f=1e-9,reference='0',evidence='supplied extraction fixture')

    def test_leaf_rlc_changes_only_run_snapshot_and_actual_pin_mapping(self):
        self.wire['parasitics']=self.model;original=deepcopy(self.document.data)
        snapshot=lower(deepcopy(original))
        self.assertEqual(self.document.data,original)
        self.assertIn('Rwire_',snapshot['source']);self.assertIn('Lwire_',snapshot['source']);self.assertIn('Cwire_',snapshot['source'])
        self.assertTrue(snapshot['wire_models'][0]['simulation_node'].startswith('spkw_'))
        from python.spikes.netlist import parse_netlist
        project=parse_netlist(snapshot['source'],native_extensions=True)
        self.assertEqual(len(project.elements),6)

    def test_invalid_extraction_is_atomic_and_revision_bound(self):
        payload=extraction_request(self.document);payload['wires']=[dict(wire_id=self.wire['id'],model=self.model)]
        before=deepcopy(self.document.data);payload['source_sha256']='wrong'
        with self.assertRaises(ValueError):import_extraction(self.document,payload)
        self.assertEqual(self.document.data,before)
        payload['source_sha256']=extraction_request(self.document)['source_sha256']
        import_extraction(self.document,payload);self.assertEqual(self.document.data['wires'][0]['parasitics'],self.model)
        self.document.undo();self.assertEqual(self.document.data,before)

    def test_unknown_reference_and_ground_return_are_not_approximated(self):
        snapshot=deepcopy(self.document.data);snapshot['wires'][0]['parasitics']=self.model|dict(reference='unknown')
        with self.assertRaisesRegex(ValueError,'reference'):lower(snapshot)
        snapshot=deepcopy(self.document.data)
        parts={p['id']:p for p in snapshot['components']}
        ground_wire=next(w for w in snapshot['wires'] if parts[w['a'][0]]['nodes'][w['a'][1]]=='0')
        ground_wire['parasitics']=self.model
        with self.assertRaisesRegex(ValueError,'Ground'):lower(snapshot)

    def test_badge_distinguishes_available_temperature_voltage_current(self):
        self.assertIsNone(badge([dict(limit='power_w',severity='unavailable')]))
        result=badge([dict(limit='voltage_v',severity='exceeded'),dict(limit='junction_temperature_c',severity='warning')])
        self.assertEqual(result['text'],'V!');self.assertTrue(result['temperature']);self.assertEqual(result['severity'],'exceeded')

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_LIBRARY'),'Native library not configured')
    def test_hidden_rlc_executes_native_dc_with_independent_resistor_oracle(self):
        from python.spikes.netlist import parse_netlist
        from python.spikes.native_runner import run_native_project
        self.document.data['source']=RC_DECK.replace('.tran 10u 5m uic','.op').replace('.end','RLOAD out 0 1k\n.end')
        self.wire['parasitics']=self.model
        snapshot=lower(deepcopy(self.document.data))
        result=run_native_project(parse_netlist(snapshot['source'],native_extensions=True),os.environ['SPIKES_TEST_LIBRARY']).to_dict()
        self.assertEqual(result['status'],'completed')
        self.assertAlmostEqual(result['data']['node_voltage_v']['out'],1000/2002,places=9)


if __name__=='__main__':unittest.main()
