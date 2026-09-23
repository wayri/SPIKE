import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.external_engines import external_engine_catalog
from python.spike_core.solver_manager import (
    recommend_emi_nets,
    recommend_solver,
    select_solver,
    register_external_solver,
    solver_manager_catalog,
    tune_solver,
    unregister_external_solver,
)
from python.spike_core.solver_plugins import default_solver_registry


class SolverManagerTests(unittest.TestCase):
    def setUp(self):
        self.state_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"SPIKE_STATE_HOME": self.state_dir.name}, clear=False)
        self.environment.start()
        self.solvers = default_solver_registry().catalog()

    def tearDown(self):
        self.environment.stop()
        self.state_dir.cleanup()

    def test_catalog_recommends_runnable_native_dc_and_gates_emi(self):
        catalog = solver_manager_catalog(self.solvers, refresh=True)
        self.assertEqual(catalog["contract"], "spike/solver-manager/v1")
        dc = next(item for item in catalog["workloads"] if item["id"] == "dc_pi")
        emi = next(item for item in catalog["workloads"] if item["id"] == "emi_radiation")
        self.assertEqual(dc["recommended"]["id"], "spike.routed_dc")
        self.assertEqual(dc["status"], "approximate")
        elmer = next(item for item in dc["candidates"] if item["id"] == "external.elmer")
        self.assertFalse(elmer["eligible"])
        self.assertEqual(elmer["model_status"], "unsupported")
        if emi["recommended"] is None:
            self.assertEqual(emi["status"], "unavailable")
        else:
            self.assertEqual(emi["recommended"]["id"], "external.openems")
            self.assertEqual(emi["status"], "reference_validated")
        self.assertFalse(catalog["installation"]["managed_downloads"])
        self.assertEqual(catalog["installation"]["remove_behavior"], "forget_registration_only")
        native_readiness = next(item for item in catalog["readiness_matrix"] if item["id"] == "spike.routed_dc")
        self.assertEqual(native_readiness["runtime"], "verified")
        self.assertEqual(native_readiness["adapter"], "not_required")
        self.assertTrue(any(item["id"] == "dc_pi" for item in native_readiness["workflows"]))

    def test_sparse_lizard_source_registration_never_enables_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "CMakeLists.txt").write_text("project(sparselizard)\n", encoding="utf-8")
            registered = register_external_solver("external.sparselizard", str(root), self.solvers)
            self.assertEqual(registered["registration"]["path"], str(root.resolve()))
            descriptor = next(
                item for item in external_engine_catalog(refresh=True)["engines"]
                if item["id"] == "external.sparselizard"
            )
            self.assertEqual(descriptor["state"], "configured_source_adapter_pending")
            self.assertEqual(descriptor["capabilities"], [])
            self.assertIn("dc_conduction", descriptor["candidate_capabilities"])
            self.assertNotIn("run", descriptor["actions"])
            removed = unregister_external_solver("external.sparselizard", self.solvers)
            self.assertTrue(removed["removed"])
            self.assertFalse(removed["files_deleted"])
            self.assertTrue(root.exists())

    def test_elmer_registration_never_claims_execution_capability(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ElmerSolver"
            executable.write_text("discovery fixture", encoding="utf-8")
            registered = register_external_solver("external.elmer", str(root), self.solvers)
            self.assertEqual(registered["registration"]["path"], str(root.resolve()))
            descriptor = next(
                item for item in external_engine_catalog(refresh=True)["engines"]
                if item["id"] == "external.elmer"
            )
            self.assertEqual(descriptor["state"], "installed_adapter_pending")
            self.assertEqual(descriptor["executable"], str(executable.resolve()))
            self.assertEqual(descriptor["capabilities"], [])
            self.assertIn("dc_conduction", descriptor["candidate_capabilities"])
            self.assertIn("solid_thermal", descriptor["candidate_capabilities"])
            self.assertNotIn("run", descriptor["actions"])
            self.assertEqual(descriptor["model_status"], "unsupported")
            self.assertIn("no bounded Elmer case translator", descriptor["reason"])
            removed = unregister_external_solver("external.elmer", self.solvers)
            self.assertTrue(removed["removed"])
            self.assertTrue(root.exists())

    def test_elmer_ignores_registered_files_that_are_not_elmer_solver(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "unrelated-tool.exe"
            candidate.write_text("not Elmer", encoding="utf-8")
            register_external_solver("external.elmer", str(candidate), self.solvers)
            descriptor = next(
                item for item in external_engine_catalog(refresh=True)["engines"]
                if item["id"] == "external.elmer"
            )
            self.assertEqual(descriptor["state"], "unavailable")
            self.assertEqual(descriptor["executable"], "")
            self.assertIn("registered", descriptor["reason"])

    def test_flotherm_registration_never_claims_execution_capability(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registered = register_external_solver("external.flotherm", str(root), self.solvers)
            self.assertEqual(registered["registration"]["path"], str(root.resolve()))
            descriptor = next(
                item for item in external_engine_catalog(refresh=True)["engines"]
                if item["id"] == "external.flotherm"
            )
            self.assertEqual(descriptor["state"], "licensed_connector_pending")
            self.assertEqual(descriptor["capabilities"], [])
            self.assertIn("conjugate_heat_transfer", descriptor["candidate_capabilities"])
            self.assertNotIn("run", descriptor["actions"])
            thermal = next(
                item for item in registered["catalog"]["workloads"]
                if item["id"] == "thermal_airflow"
            )
            flotherm = next(item for item in thermal["candidates"] if item["id"] == "external.flotherm")
            self.assertFalse(flotherm["eligible"])

    def test_adapter_pending_engines_expose_only_candidate_capabilities(self):
        descriptors = {
            item["id"]: item for item in external_engine_catalog(refresh=True)["engines"]
        }
        for engine_id in ("external.elmer", "external.fasthenry", "external.fastcap", "external.openfoam"):
            descriptor = descriptors[engine_id]
            self.assertEqual(descriptor["capabilities"], [])
            self.assertTrue(descriptor["candidate_capabilities"])

    def test_tuning_is_allowlisted_and_range_checked(self):
        result = tune_solver("native.sparse", {"linear_backend": "superlu", "thread_count": 4}, self.solvers)
        self.assertEqual(result["configured"]["thread_count"], 4)
        with self.assertRaisesRegex(ValueError, "between"):
            tune_solver("native.sparse", {"thread_count": 0}, self.solvers)
        with self.assertRaisesRegex(ValueError, "Unknown tuning keys"):
            tune_solver("external.openems", {"raw_solver_arguments": "--unsafe"}, self.solvers)

    def test_recommendation_rejects_unknown_workload(self):
        recommendation = recommend_solver("quasistatic_ac_pi", self.solvers)
        peec = next(item for item in self.solvers if item["id"] == "spike.peec_2_5d")
        if peec["state"] in {"available", "experimental", "reference_validated", "validated"}:
            self.assertEqual(recommendation["workload"]["recommended"]["id"], "spike.peec_2_5d")
        else:
            self.assertIsNone(recommendation["workload"]["recommended"])
            self.assertEqual(recommendation["workload"]["status"], "unavailable")
        with self.assertRaisesRegex(ValueError, "Unknown solver workload"):
            recommend_solver("magic_rf", self.solvers)

    def test_explicit_selection_never_substitutes_a_solver(self):
        selected = select_solver("dc_pi", "spike.routed_dc", self.solvers)
        self.assertEqual(selected["contract"], "spike/solver-selection/v1")
        self.assertEqual(selected["status"], "selected")
        self.assertEqual(selected["selected"]["id"], "spike.routed_dc")
        self.assertEqual(selected["selection_policy"], "explicit_solver_only_no_fallback")
        self.assertEqual(selected["selected"]["source"], "native")

        blocked = select_solver("dc_pi", "external.openems", self.solvers)
        self.assertEqual(blocked["status"], "blocked")
        self.assertIsNone(blocked["selected"])
        self.assertIn("not declared", blocked["reason"])
        with self.assertRaisesRegex(ValueError, "concrete solver_id"):
            select_solver("dc_pi", "auto", self.solvers)

    def test_native_mna_is_selectable_only_for_explicit_linear_workspaces(self):
        selection = select_solver("linear_circuit_workspace", "spike.native_mna", self.solvers)
        self.assertEqual(selection["status"], "selected")
        selected = selection["selected"]
        self.assertEqual(selected["request_contract"], "spike/native-mna-request/v1")
        self.assertEqual(selected["execution"], "workspace_contract")
        self.assertIn("no PCB geometry extraction", selected["scope"])

        blocked = select_solver("dc_pi", "spike.native_mna", self.solvers)
        self.assertEqual(blocked["status"], "blocked")
        self.assertIn("not declared", blocked["reason"])

    def test_owned_workspace_is_a_runtime_probed_circuit_workload_not_cosimulation(self):
        ready_status = {
            "available": True,
            "abi_version": "test-abi",
            "features": {"transient": True},
        }
        with patch("python.spike_core.solver_manager.engine_status", return_value=ready_status):
            catalog = solver_manager_catalog(self.solvers, refresh=True)
            owned = next(item for item in catalog["workloads"] if item["id"] == "owned_circuit_workspace")
            selection = select_solver(
                "owned_circuit_workspace", "spike.owned_spice_workspace", self.solvers,
            )
            cosim = select_solver(
                "circuit_cosimulation", "spike.owned_spice_workspace", self.solvers,
            )

        self.assertEqual(owned["status"], "experimental")
        self.assertEqual(owned["recommended"]["id"], "spike.owned_spice_workspace")
        self.assertEqual(selection["status"], "selected")
        self.assertEqual(selection["selected"]["execution"], "owned_workspace_contract")
        self.assertEqual(selection["selected"]["request_contract"], "spike/owned-spice-workspace-request/v1")
        self.assertIn("No raw netlist", selection["selected"]["scope"])
        self.assertEqual(cosim["status"], "blocked")
        self.assertIn("not declared", cosim["reason"])

    def test_owned_workspace_fails_closed_when_runtime_probe_is_incomplete(self):
        with patch(
            "python.spike_core.solver_manager.engine_status",
            return_value={"available": True, "features": {"transient": False}},
        ):
            selection = select_solver(
                "owned_circuit_workspace", "spike.owned_spice_workspace", self.solvers,
            )
        self.assertEqual(selection["status"], "blocked")
        self.assertEqual(selection["candidate"]["state"], "unavailable")
        self.assertEqual(selection["candidate"]["missing"], [
            "explicit_circuit_workspace", "operating_point", "transient_waveforms", "release_owned_engine",
        ])
        self.assertIn("runtime", selection["reason"])

    def test_unavailable_catalogue_entry_uses_its_validation_as_the_block_reason(self):
        selection = select_solver("fullwave_comparison", "spike.fullwave_3d", self.solvers)
        self.assertEqual(selection["status"], "blocked")
        self.assertEqual(selection["candidate"]["state"], "unavailable")
        self.assertEqual(selection["reason"], "No validated full-wave engine is packaged.")

    def test_openems_selection_depends_on_the_live_external_descriptor(self):
        openems = {
            "id": "external.openems",
            "name": "openEMS FDTD",
            "state": "reference_validated",
            "model_status": "reference_validated",
            "capabilities": ["far_field", "ports", "lossy_dielectrics"],
            "actions": ["detect", "prepare", "run"],
            "interface": "process",
            "adapter_version": "test-adapter",
            "validation": "A bounded reference fixture passed.",
        }
        with patch("python.spike_core.solver_manager.external_engine_catalog", return_value={"engines": [openems]}):
            selected = select_solver("emi_radiation", "external.openems", self.solvers, refresh=True)
        self.assertEqual(selected["status"], "selected")
        self.assertEqual(selected["selected"]["id"], "external.openems")
        self.assertEqual(selected["selected"]["source"], "external")
        self.assertEqual(selected["selected"]["execution"], "process")
        self.assertEqual(selected["selected"]["adapter_version"], "test-adapter")

    def test_worker_exposes_explicit_selection_without_fallback(self):
        from python.spike_core.service import handle

        selected = handle({
            "method": "select_solver",
            "params": {"workload_id": "dc_pi", "solver_id": "spike.routed_dc"},
        })
        self.assertTrue(selected["ok"])
        self.assertEqual(selected["result"]["status"], "selected")
        self.assertEqual(selected["result"]["selected"]["id"], "spike.routed_dc")

        invalid = handle({
            "method": "select_solver",
            "params": {"workload_id": "dc_pi", "solver_id": "auto"},
        })
        self.assertFalse(invalid["ok"])
        self.assertIn("concrete solver_id", invalid["error"])

    def test_emi_prepass_is_deterministic_screening_not_compliance(self):
        result = recommend_emi_nets([
            {"net": "quiet", "dv_dt_v_per_s": 1e3, "di_dt_a_per_s": 1e2, "peak_current_a": 0.1},
            {"net": "switch", "dv_dt_v_per_s": 1e9, "di_dt_a_per_s": 1e7, "peak_current_a": 10, "loop_area_mm2": 100},
        ])
        self.assertEqual(result["status"], "screening_only")
        self.assertEqual(result["recommended_nets"][0]["net"], "switch")
        self.assertIn("not a radiation prediction", result["warning"])


if __name__ == "__main__":
    unittest.main()
