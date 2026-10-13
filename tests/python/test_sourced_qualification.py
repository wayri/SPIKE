# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import hashlib
from pathlib import Path
import tempfile
import unittest

from python.spikes.sourced_qualification import qualify_sourced_deck


def fixture(path,deck):
    path.write_text(deck,encoding='utf-8')
    return {'contract':'spikes/sourced-qualification-request/v1','id':'original-divider','deck_path':path.name,
            'purpose':'solver_regression','pin_mapping':{},
            'sources':[{'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'role':'deck',
                        'origin':'Original independent analytical fixture','revision':'1',
                        'conditions':'Ideal resistor/RC only, no hardware device','value_basis':'synthetic'}],
            'checks':[{'probe':'V(out)','measurement':'last','threshold':0.,'minimum':1.649999,'maximum':1.650001,
                       'numerical_absolute_tolerance':1e-3,'numerical_relative_tolerance':1e-3}]}


class SourcedQualificationTests(unittest.TestCase):
    def test_includes_consume_immutable_admitted_text(self):
        from python.spikes.netlist import parse_netlist, NetlistParseError
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root/'cell.lib'
            snapshot = '.subckt cell a b\nR1 a b 1000\n.ends cell\n'
            model.write_text(snapshot)
            main = root/'deck.cir'
            deck = '* Original immutable include test\n.include "cell.lib"\nV1 in 0 1\nX1 in 0 cell\n.op\n.end\n'
            main.write_text(deck)
            model.write_text(snapshot.replace('1000','9000'))
            project = parse_netlist(deck,source_name=str(main),source_snapshots={str(model.resolve()):snapshot})
            self.assertEqual(next(e.value for e in project.elements if e.kind=='resistor'),1000)
            with self.assertRaises(NetlistParseError):
                parse_netlist(deck,source_name=str(main),source_snapshots={})

    def test_native_event_steps_are_actually_capped(self):
        from python.spikes.netlist import parse_netlist
        from python.spikes.native_runner import run_native_project
        from python.spike_core.spikes_runtime import owned_library_path
        project = parse_netlist('* Original step-budget test\nV1 a 0 PULSE(0 1 0 1u 1u 50u 100u)\nR1 a 0 1000\n.tran 5m 10m uic\n.end\n',native_extensions=True)
        # Nominal .tran samples are only three; waveform edges demand more.
        answer = run_native_project(project,owned_library_path(),maximum_steps=10)
        self.assertEqual(answer.status,'failed')

    def test_actual_native_divider_and_artifact_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            request = fixture(Path(directory)/'deck.cir','Original\nV1 in 0 3.3\nR1 in out 1k\nR2 out 0 1k\n.op\n.end\n')
            answer = qualify_sourced_deck(request,directory)
        self.assertEqual(answer['status'],'PASS')
        self.assertFalse(answer['hardware_qualified'])
        self.assertAlmostEqual(answer['gates'][0]['observed'],1.65,places=10)
        self.assertEqual(answer['sources'],request['sources'])
        self.assertEqual(len(answer['solver']['library_sha256']),64)

    def test_owned_native_switch_subset_is_not_misreported_unsupported(self):
        with tempfile.TemporaryDirectory() as directory:
            request = fixture(Path(directory)/'deck.cir','* Original native smooth-switch fixture\nV1 in 0 1\nV2 ctl 0 1\nS1 in out ctl 0 1 1e9 .5 .001\nR1 out 0 100\n.op\n.end\n')
            request['checks'][0].update(minimum=.990098,maximum=.990101)
            self.assertEqual(qualify_sourced_deck(request,directory)['status'],'PASS')

    def test_actual_rc_three_steps_and_threshold_event(self):
        with tempfile.TemporaryDirectory() as directory:
            request = fixture(Path(directory)/'deck.cir','Original RC\nV1 in 0 1\nR1 in out 1k\nC1 out 0 1u\n.tran 10u 5m uic\n.end\n')
            request['checks'][0].update(measurement='first_rising_crossing',threshold=.5,minimum=.00068,maximum=.00071,
                                         numerical_absolute_tolerance=1e-5,numerical_relative_tolerance=.01)
            answer = qualify_sourced_deck(request,directory)
        self.assertEqual(answer['status'],'PASS',answer['gates'])
        self.assertEqual(len(answer['runs']),3)
        self.assertTrue(answer['gates'][0]['refinement_passed'])
        for actual,expected in zip([r['output_step_s'] for r in answer['runs']],[1e-5,5e-6,2.5e-6],strict=True):
            self.assertAlmostEqual(actual,expected,places=18)

    def test_absent_event_and_bad_physical_limit_do_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            request = fixture(Path(directory)/'deck.cir','Original\nV1 out 0 1\nR1 out 0 1k\n.op\n.end\n')
            self.assertEqual(qualify_sourced_deck(request,directory)['status'],'FAIL')
            request['checks'][0].update(measurement='first_rising_crossing',threshold=2)
            answer = qualify_sourced_deck(request,directory)
            self.assertEqual(answer['status'],'FAIL')
            self.assertIsNone(answer['gates'][0]['observed'])

    def test_refinement_uses_larger_tolerance_not_sum_of_tolerances(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            request = fixture(Path(directory)/'deck.cir','* Original gate fixture\nV1 out 0 1\nR1 out 0 1000\n.tran 1m 2m\n.end\n')
            request['checks'][0].update(minimum=.9,maximum=1.1)
            answers = [SimpleNamespace(status='completed',diagnostics={},issues=[],
                       data={'time_s':[0.,.002],'node_voltage_v':{'out':[1.,value]}})
                       for value in (1.,1.0015,1.0015)]
            with patch('python.spikes.sourced_qualification.run_native_project',side_effect=answers):
                answer = qualify_sourced_deck(request,directory)
        self.assertEqual(answer['status'],'FAIL')
        self.assertTrue(answer['gates'][0]['acceptance_passed'])
        self.assertFalse(answer['gates'][0]['refinement_passed'])

    def test_unrepresentable_acceptance_number_is_coded(self):
        with tempfile.TemporaryDirectory() as directory:
            request = fixture(Path(directory)/'deck.cir','* Original\nV1 out 0 1\nR1 out 0 1000\n.op\n.end\n')
            request['checks'][0]['maximum'] = 10**1000
            with self.assertRaisesRegex(ValueError,'unrepresentable number'):
                qualify_sourced_deck(request,directory)

    def test_hash_unknown_field_and_unlisted_include_fail_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'deck.cir'
            request = fixture(path,'Original\nV1 out 0 1\nR1 out 0 1k\n.op\n.end\n')
            path.write_text('changed')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                qualify_sourced_deck(request,directory)
            request = fixture(path,'Original\n.include "unlisted.lib"\n.op\n.end\n')
            with self.assertRaisesRegex(ValueError,'unlisted include'):
                qualify_sourced_deck(request,directory)
            request['unexpected'] = True
            with self.assertRaisesRegex(ValueError,'unknown/missing'):
                qualify_sourced_deck(request,directory)

    def test_unsupported_model_is_blocked_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            request = fixture(Path(directory)/'deck.cir','Original\n.model unknown UNSUPPORTED_LEVEL(X=1)\n.op\n.end\n')
            answer = qualify_sourced_deck(request,directory)
        self.assertEqual(answer['status'],'BLOCKED')
        self.assertFalse(answer['hardware_qualified'])
        self.assertTrue(answer['compatibility_error'])

    def test_guided_examples_and_immutable_csv_svg_hash_manifest(self):
        import json
        import xml.etree.ElementTree as ET
        from examples.sas_qualification.run_reference import run
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'evidence'
            results = run(root)
            self.assertEqual([r['status'] for r in results],['PASS','PASS'])
            manifest = json.loads((root/'rc-fault-bus-reference-evidence'/'COMMITTED.json').read_text())
            self.assertFalse(manifest['vendor_models_redistributed'])
            for item in manifest['files']:
                path = root/'rc-fault-bus-reference-evidence'/item['path']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),item['sha256'])
                if path.suffix=='.svg': ET.parse(path)
            with self.assertRaises(FileExistsError): run(root)

    def test_thermal_example_exports_bounded_synthetic_feedback_evidence(self):
        import json
        from examples.sas_qualification.run_thermal_reference import run
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'thermal'
            summary = run(root)
            report = json.loads((root/'result.json').read_text())
        self.assertEqual(summary['status'],'PASS')
        self.assertFalse(summary['hardware_qualified'])
        self.assertLess(max(summary['steady_error_k'].values()),1e-6)
        self.assertIn('not SAS installed cooling',report['scope'])
