import tempfile
import unittest
from pathlib import Path

from python.spike_core.assembly_analysis_scope import (
    AssemblyAnalysisScopeError,
    validate_assembly_analysis_scope,
    validate_case_scope,
    write_case_scope,
)
from python.spike_core.contracts import DesignIR
from python.spike_core.service import handle


def assembly():
    return {
        "contract": "spike/assembly-ir/v1",
        "assembly_id": "assembly-1",
        "name": "Two-board fixture",
        "frame": {"frame_id": "assembly"},
        "boards": [
            {"id": "board-a", "name": "A", "design_id": "design-a", "frame": {"frame_id": "frame-a", "parent_frame_id": "assembly"}},
            {"id": "board-b", "name": "B", "design_id": "design-b", "frame": {"frame_id": "frame-b", "parent_frame_id": "assembly"}},
        ],
        "harnesses": [{"id": "harness-1", "name": "H", "endpoint_a": "board-a:J1", "endpoint_b": "board-b:J1"}],
        "connector_mappings": [], "rigid_flex_links": [],
        "parts": [{"id": "case", "name": "Case", "model_id": "model-case", "frame": {"frame_id": "case-frame", "parent_frame_id": "assembly"}}],
        "materials": [], "thermal_contacts": [], "electrical_bonds": [],
    }


def scope(**overrides):
    value = {
        "contract": "spike/assembly-analysis-scope/v1",
        "mode": "active_board_only",
        "assembly": assembly(),
        "active_board_id": "board-a",
        "active_design_id": "design-a",
    }
    value.update(overrides)
    return value


class AssemblyAnalysisScopeTests(unittest.TestCase):
    def test_active_board_scope_records_every_ignored_entity(self):
        result = validate_assembly_analysis_scope(scope(), DesignIR(design_id="design-a"))
        self.assertFalse(result["assembly_coupling"])
        self.assertEqual(result["ignored_entities"]["boards"], ["board-b"])
        self.assertEqual(result["ignored_entities"]["harnesses"], ["harness-1"])
        self.assertEqual(result["ignored_entities"]["parts"], ["case"])
        self.assertEqual(len(result["scope_digest"]), 64)

    def test_ambiguous_or_coupled_scope_fails_closed(self):
        with self.assertRaises(AssemblyAnalysisScopeError):
            validate_assembly_analysis_scope(scope(active_board_id="missing"), DesignIR(design_id="design-a"))
        with self.assertRaises(AssemblyAnalysisScopeError):
            validate_assembly_analysis_scope(scope(active_design_id="design-b"), DesignIR(design_id="design-a"))
        with self.assertRaises(AssemblyAnalysisScopeError):
            validate_assembly_analysis_scope(scope(mode="assembly_coupled"), DesignIR(design_id="design-a"))

    def test_prepared_case_requires_the_exact_bound_scope(self):
        normalized = validate_assembly_analysis_scope(scope(), DesignIR(design_id="design-a"))
        with tempfile.TemporaryDirectory() as directory:
            write_case_scope(directory, normalized)
            self.assertEqual(validate_case_scope(directory, normalized), normalized)
            with self.assertRaises(AssemblyAnalysisScopeError):
                validate_case_scope(directory, None)
            changed = dict(normalized)
            changed["active_board_id"] = "board-b"
            with self.assertRaises(AssemblyAnalysisScopeError):
                validate_case_scope(directory, changed)
            self.assertTrue((Path(directory) / "spike_assembly_scope.json").is_file())

    def test_worker_blocks_coupled_scope_before_solver_dispatch(self):
        for method in (
            "run_analysis", "preflight_analysis", "run_spice_workspace_native_mna",
            "run_field_circuit_cosimulation", "prepare_openems_case", "prepare_thermal_case",
            "run_openems_case", "run_thermal_case",
        ):
            with self.subTest(method=method):
                response = handle({
                    "id": f"coupled-{method}", "method": method,
                    "params": {
                        "design": {"design_id": "design-a"}, "spec": {"mode": "dc"},
                        "assembly_scope": scope(mode="assembly_coupled"),
                    },
                })
                self.assertFalse(response["ok"])
                self.assertEqual(response["error_code"], "SPIKE-BE-IPC-E-0001")
                self.assertIn("Coupled assembly physics", response["error_detail"]["detail"])

    def test_worker_result_provenance_preserves_active_board_scope(self):
        response = handle({
            "method": "run_analysis",
            "params": {
                "design": {"design_id": "design-a"},
                "spec": {"analysis_id": "scoped", "mode": "dc"},
                "assembly_scope": scope(),
            },
        })
        self.assertTrue(response["ok"])
        provenance = response["result"]["provenance"]["assembly_analysis_scope"]
        self.assertEqual(provenance["active_board_id"], "board-a")
        self.assertFalse(provenance["assembly_coupling"])


if __name__ == "__main__":
    unittest.main()
