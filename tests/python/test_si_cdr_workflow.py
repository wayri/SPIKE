# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.python.test_si_exact_clock import through
from python.spike_core.si_workflow import run_si_workflow
from python.spike_core.si_clock_recovery import recover_nrz_clock


def request():
    q = through(samples=32)
    q["sources"][0].update(rise_time_s=20e-12, fall_time_s=20e-12)
    q["receivers"][0]["cdr"] = {"kind": "transition_pi", "threshold_v": .25,
                                "normalization_v": .5, "initial_phase_ui": .1}
    return q


class CdrWorkflowTests(unittest.TestCase):
    def test_checked_example_symbol_decisions(self):
        from scripts.qualify_cdr_workflow import qualification_report
        report = qualification_report()
        self.assertEqual(report["status"], "pass")
        self.assertGreaterEqual(report["observed_symbols"], 800)
        self.assertEqual(report["observed_symbol_errors"], 0)
        self.assertFalse(report["production_qualified"])

    def test_full_waveform_not_decimated_export_reaches_cdr(self):
        with patch("python.spike_core.si_workflow.recover_nrz_clock", wraps=recover_nrz_clock) as recovery:
            result = run_si_workflow(request())
        rx = result["time_domain"]["receivers"][0]
        self.assertEqual(result["time_domain"]["status"], "completed")
        self.assertEqual(rx["clock_recovery"]["status"], "tracking")
        self.assertGreater(len(recovery.call_args.args[0]), len(rx["waveform"]))
        self.assertFalse(result["production_qualified"])
        self.assertEqual(result["compliance_status"], "not_evaluated")
        json.dumps(result, allow_nan=False)

    def test_schema_and_runtime_admission(self):
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        root = Path(__file__).resolve().parents[2]
        documents = [json.loads(p.read_text()) for p in (root / "schemas").glob("si-*.schema.json")]
        registry = Registry().with_resources((d["$id"], Resource.from_contents(d)) for d in documents)
        schema = next(d for d in documents if d["$id"].endswith("si-workflow-request-v1.schema.json"))
        Draft202012Validator(schema, registry=registry).validate(request())
        q = request(); q["receivers"][0]["cdr"]["unexpected"] = True
        with self.assertRaises(ValueError):
            run_si_workflow(q)

    def test_cdr_must_not_be_silently_ignored(self):
        q = request(); q["run_time_domain"] = False
        with self.assertRaisesRegex(ValueError, "requires run_time_domain"):
            run_si_workflow(q)
        q = request(); q["sources"][0]["cdr"] = q["receivers"][0].pop("cdr")
        with self.assertRaises(ValueError):
            run_si_workflow(q)

    def test_without_cdr_existing_output_stays_opt_in(self):
        r = run_si_workflow(through())
        self.assertNotIn("clock_recovery", r["time_domain"]["receivers"][0])
