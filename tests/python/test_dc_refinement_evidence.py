# SPDX-License-Identifier: Apache-2.0
"""Independent small native-source refinement evidence and tamper regressions."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import benchmark_board_volume_dc as native_benchmark
from scripts import benchmark_board_volume_scaling as scaling_benchmark
from scripts import verify_board_volume_refinement as verifier
from tests.python.test_dc_board_source import FIXTURE, ROOT


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")


class RefinementEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="refinement-oracle-", dir=ROOT/"build")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.folder = Path(cls.temporary.name).resolve()
        cls.study = "fixture-fullpads"
        study = {"board": "fixture", "net": "VDD", "electrodes":
                 [("J1.1", "F.Cu", "top", 1.), ("J1.2", "F.Cu", "top", -1.)],
                 "scope": "Synthetic native SMD refinement evidence test only."}
        audit_folder = cls.folder/"native"; audit_folder.mkdir()
        with patch.object(native_benchmark, "BOARDS", {"fixture": (FIXTURE.relative_to(ROOT).as_posix(), digest(FIXTURE))}), \
                patch.object(native_benchmark, "STUDIES", {cls.study: study}), redirect_stdout(io.StringIO()):
            native_benchmark.execute(audit_folder, "fixture")
        cls.audit = audit_folder/"fixture-audit.json"
        cls.model = ROOT/read(cls.audit)["studies"][cls.study]["model"]
        cls.ladder = cls.folder/"ladder"
        argv = ["benchmark_board_volume_scaling.py", "--model", str(cls.model), "--output", str(cls.ladder),
                "--targets", "1", ".5", ".25", "--timeout", "60", "--solve"]
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            scaling_benchmark.main()
        cls.cases = [cls.ladder/str(i)/"case-report.json" for i in range(3)]
        for case in cls.cases:
            report = read(case)
            if report["status"] != "discrete_fields_verified":
                raise AssertionError("Actual fixture solve failed: " + str(report.get("blocker")))
        cls.baseline = {p: p.read_bytes() for p in cls.folder.rglob("*.json")}

    def setUp(self):
        for path, contents in self.baseline.items():
            path.write_bytes(contents)

    def verify(self, **kwargs):
        return verifier.verify(self.cases, self.audit, self.study, **kwargs)

    def refresh_case_binding(self, index=0):
        summary_path = self.ladder/"summary.json"; summary = read(summary_path)
        row = summary["cases"][index]
        row["report_sha256"] = digest(self.cases[index])
        row["model_sha256"] = digest(self.cases[index].parent/"model.json")
        write(summary_path, summary)

    def change_fields(self, mutate, index=0):
        path = self.cases[index].parent/"fields.json"; data = read(path); mutate(data); write(path, data)
        report = read(self.cases[index]); report["fields_sha256"] = digest(path); write(self.cases[index], report)
        self.refresh_case_binding(index)

    def test_three_actual_supervised_levels_replay_without_overclaim(self):
        result = self.verify()
        self.assertIn(result["status"], ("passed_refinement_stability", "needs_further_refinement"))
        self.assertTrue(result["retained_fields_replayed"])
        for key in ("stage_complete", "production_qualified", "full_board_pisi_ready"):
            self.assertIs(result[key], False)
        self.assertEqual([level["target_mm"] for level in result["levels"]], [1., .5, .25])
        self.assertEqual(len(result["successive_relative_changes"]), 2)
        expected = all(step[key] <= limit for step in result["successive_relative_changes"]
                       for key, limit in result["frozen_relative_limits"].items())
        self.assertEqual(result["status"] == "passed_refinement_stability", expected)
        self.assertTrue(all(level["cells"] < 50000 for level in result["levels"]))
        for level in result["levels"]:
            self.assertAlmostEqual(level["physical_volume_m3"], 3*.035*1e-9, delta=1e-23)

    def test_missing_method_manifest_is_not_vacuously_current(self):
        report = read(self.cases[0]); report["methods_before"] = {}; report["methods_after"] = {}
        write(self.cases[0], report); self.refresh_case_binding()
        with self.assertRaises(ValueError): self.verify()

    def test_method_digest_drift_rejects(self):
        report = read(self.cases[0]); name = next(iter(report["methods_before"]))
        report["methods_before"][name] = report["methods_after"][name] = "0"*64
        write(self.cases[0], report); self.refresh_case_binding()
        with self.assertRaises(ValueError): self.verify()

    def test_summary_binds_report_model_and_authenticated_parent(self):
        summary_path = self.ladder/"summary.json"
        for mutate in (lambda s: s["cases"][0].__setitem__("report_sha256", "0"*64),
                       lambda s: s["cases"][0].__setitem__("model_sha256", "0"*64),
                       lambda s: s.__setitem__("source_model", str(FIXTURE)),
                       lambda s: s.__setitem__("source_model_sha256_before", "0"*64)):
            with self.subTest(mutation=mutate):
                self.setUp(); summary = read(summary_path); mutate(summary); write(summary_path, summary)
                with self.assertRaises(ValueError): self.verify()

    def test_process_and_memory_evidence_cannot_be_omitted_or_waived(self):
        summary_path = self.ladder/"summary.json"
        for mutate in (lambda s: s["cases"][0]["process"].__setitem__("memory_limit_enforced", False),
                       lambda s: s["cases"][0]["process"].__setitem__("return_code", 1),
                       lambda s: s["process_policy"].__setitem__("memory_limit_mb", 0),
                       lambda s: s["process_policy"].__setitem__("timeout_s", 601)):
            with self.subTest(mutation=mutate):
                self.setUp(); summary = read(summary_path); mutate(summary); write(summary_path, summary)
                with self.assertRaises(ValueError): self.verify()
        self.setUp(); report = read(self.cases[0]); report["native_memory"] = {}
        write(self.cases[0], report); self.refresh_case_binding()
        with self.assertRaises(ValueError): self.verify()

    def test_physical_model_field_and_scope_forgeries_reject_even_with_fresh_hashes(self):
        model_path = self.cases[0].parent/"model.json"; model = read(model_path)
        model["groups"][0]["conductivity_s_m"] *= 2; write(model_path, model)
        report = read(self.cases[0]); report["model_sha256"] = digest(model_path); write(self.cases[0], report)
        self.refresh_case_binding()
        with self.assertRaises(ValueError): self.verify()
        for mutate in (lambda r: r["cells"][0]["vertex_density_a_m2"][0].__setitem__(0, 1e30),
                       lambda r: r.__setitem__("production_qualified", True)):
            self.setUp(); self.change_fields(mutate)
            with self.assertRaises(ValueError): self.verify()
        self.setUp(); report = read(self.cases[0]); report["stage_complete"] = True
        write(self.cases[0], report); self.refresh_case_binding()
        with self.assertRaises(ValueError): self.verify()

    def test_bound_artifact_change_during_replay_rejects(self):
        from python.spike_core.solvers.power_integrity.dc.dc_tetra_rt0_evidence import validate_tetra_dc
        changed = False
        def validate_then_change(result):
            nonlocal changed
            validate_tetra_dc(result)
            if not changed:
                changed = True
                data = read(self.cases[0]); data["elapsed_s"] += 1; write(self.cases[0], data)
        with patch("python.spike_core.solvers.power_integrity.dc.dc_tetra_rt0_evidence.validate_tetra_dc", side_effect=validate_then_change), \
                self.assertRaises(ValueError):
            self.verify()

    def test_model_is_snapshotted_before_reading_its_physical_contents(self):
        model_path = self.cases[0].parent/"model.json"
        replacement = read(model_path); replacement["groups"][0]["conductivity_s_m"] *= 2
        replacement_bytes = json.dumps(replacement, allow_nan=False).encode()
        replacement_sha = hashlib.sha256(replacement_bytes).hexdigest()
        report = read(self.cases[0]); report["model_sha256"] = replacement_sha; write(self.cases[0], report)
        self.refresh_case_binding()
        summary_path = self.ladder/"summary.json"; summary = read(summary_path)
        summary["cases"][0]["model_sha256"] = replacement_sha; write(summary_path, summary)
        original_load = verifier.load
        def load_then_replace(path):
            value = original_load(path)
            if path == model_path:
                model_path.write_bytes(replacement_bytes)
            return value
        with patch.object(verifier, "load", side_effect=load_then_replace), self.assertRaises(ValueError):
            self.verify()

    def test_inspection_without_field_replay_never_accepts_stability(self):
        result = self.verify(replay=False)
        self.assertNotIn(result["status"], ("passed_selected_study", "passed_refinement_stability"))
        self.assertFalse(result["retained_fields_replayed"])

    def test_unfrozen_target_ladder_rejects_even_during_inspection(self):
        for index, target in enumerate((1., .75, .5)):
            path = self.cases[index].parent/"model.json"; model = read(path)
            model["target_mm"] = target; write(path, model)
            report = read(self.cases[index]); report["model_sha256"] = digest(path)
            write(self.cases[index], report); self.refresh_case_binding(index)
        with self.assertRaises(ValueError): self.verify(replay=False)

    def test_zero_quantile_comparisons_are_finite_and_never_physical_acceptance(self):
        # These mutated fields are deliberately inspected WITHOUT physical replay.
        # This checks the comparison branch only, not a fabricated accepted solve.
        for index in range(3):
            self.change_fields(lambda r: r["current_density_observable"]["p95"].__setitem__("upper_a_m2", 0.), index)
        result = self.verify(replay=False)
        self.assertEqual(result["status"], "inspection_only")
        self.assertEqual([step["p95_a_m2"] for step in result["successive_relative_changes"]], [0., 0.])
        self.change_fields(lambda r: r["current_density_observable"]["p95"].__setitem__("upper_a_m2", 1.), 1)
        result = self.verify(replay=False)
        self.assertEqual([step["p95_a_m2"] for step in result["successive_relative_changes"]], [1., 1.])
        json.dumps(result, allow_nan=False)

    def test_both_successive_deltas_remain_visible_when_last_step_is_stable(self):
        # An exact last-step match must not hide a large earlier change.
        for index, value in enumerate((1., 2., 2.)):
            self.change_fields(lambda r, v=value: r["current_density_observable"]["p99"].__setitem__("upper_a_m2", v), index)
        result = self.verify(replay=False)
        self.assertEqual([step["p99_a_m2"] for step in result["successive_relative_changes"]], [1., 0.])
        self.assertEqual(result["status"], "inspection_only")


if __name__ == "__main__":
    unittest.main()
