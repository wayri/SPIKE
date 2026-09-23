import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from python.spike_core.thermal_field_job import (
    PLAN_CONTRACT,
    REQUEST_CONTRACT,
    ThermalFieldJobError,
    execute_thermal_field_job,
    plan_thermal_field_job,
)
from python.spike_core.thermal_qualification import QUALIFICATION_CONTRACT, required_qualification_gates
from python.spike_core.service import handle


ROOT = Path(__file__).resolve().parents[2]


ALL_PHYSICS = [
    "solid_conduction", "transient_conduction", "thermal_contacts", "material_properties", "coatings",
    "component_heat_source_table", "package_shapes", "mcad_parts", "enclosure", "heatsinks", "fans",
    "potting", "vacuum_radiation", "radiation", "airflow", "conjugate_heat_transfer", "electrothermal_iteration",
]


def request() -> dict:
    return {
        "contract": REQUEST_CONTRACT,
        "job_id": "thermal-fixture",
        "scenario": {
            "mode": "conjugate_heat_transfer", "medium": "potting", "enclosure": "sealed", "convection": "forced",
            "bounding_volume_mm": {"x": 100, "y": 80, "z": 30}, "mesh": {"cell_size_mm": 2, "max_cells": 1_000_000},
            "thermal_elements": [{"id": "u1"}], "thermal_links": [{"id": "tim"}], "component_bonds": [{"id": "bond"}],
            "material_library": [{"id": "fr4"}], "surface_finish_library": [{"id": "conformal"}],
            "heat_sources": [{"id": "u1", "power_w": 3}], "virtual_heatsinks": [{"id": "hs"}],
            "fans": [{"id": "fan"}], "flow_channels": [{"id": "duct"}], "options": {"radiation": True},
            "electrothermal": {"enabled": True},
        },
        "requested_physics": ALL_PHYSICS,
        "solver_selection": {"solver_id": "fixture.qualified_thermal"},
        "geometry": {"qualified_geometry": True, "mesh_evidence_id": "mesh:fixture", "contact_evidence_id": "contact:fixture", "assembly_shape_evidence_id": "shape:fixture", "mcad_geometry_evidence_id": "mcad:fixture"},
        "resource_budget": {"max_cells": 100_000, "max_output_samples": 1000, "memory_limit_mb": 1024, "cpu_time_limit_s": 300},
        "cancellation_enabled": True,
    }


def qualified_catalog() -> dict:
    fixtures = []
    gates = required_qualification_gates(ALL_PHYSICS)
    for index, gate in enumerate(gates):
        reference_type = "analytic"
        if gate == "independent_correlation":
            reference_type = "independent_solver"
        elif gate == "measured_correlation":
            reference_type = "measured"
        fixtures.append({
            "id": f"fixture-{gate}", "gate": gate, "status": "passed",
            "fixture_sha256": f"{index + 1:064x}", "result_sha256": f"{index + 101:064x}",
            "reference_type": reference_type, "reference_id": f"reference:{gate}",
            "tolerance": 0.01, "observed": 0.001,
        })
    return {
        "fixture.qualified_thermal": {
            "id": "fixture.qualified_thermal", "name": "Qualified fixture engine", "version": "1.0", "state": "validated",
            "model_status": "validated", "execution": "isolated_process", "actions": ["prepare", "run"],
            "capabilities": ALL_PHYSICS,
            "qualification_evidence": {
                "contract": QUALIFICATION_CONTRACT, "evidence_id": "thermal-fixture-evidence",
                "solver": {"id": "fixture.qualified_thermal", "version": "1.0"},
                "platforms": ["windows-x64", "linux-x64"], "capabilities": ALL_PHYSICS,
                "fixtures": fixtures,
            },
        }
    }


class ThermalFieldJobTests(unittest.TestCase):
    def _adapter(self, *, probe_status: str = "passed", total_samples: int = 1):
        class Adapter:
            calls = 0

            def probe(self):
                return {
                    "contract": "spike/solver-plugin-probe-result/v1", "status": probe_status,
                    "runtime": {"name": "fixture", "version": "1"},
                    "adapter": {"version": "1", "protocol": "spike/solver-plugin/v1"},
                }

            def run(self, invocation):
                self.calls += 1
                field = {
                    "unit": "K", "samples": [{"point_mm": [0, 0, 0], "value": 310.0, "region": "solid"}],
                    "total_samples": total_samples,
                }
                if total_samples > 1:
                    field["artifact"] = {"id": "temperature-field", "sha256": "a" * 64, "bytes": 128, "contract": "spike/thermal-field-chunk/v1"}
                return {
                    "contract": "spike/thermal-field-result/v1", "job_id": invocation["job_id"], "plan_digest": invocation["plan_digest"],
                    "status": "completed", "model_status": "reference_validated", "summary": {"max_temperature_k": 310.0},
                    "fields": {"temperature_k": field}, "component_temperatures_k": {"U1": 310.0},
                    "issues": [], "provenance": {"solver_id": "fixture.qualified_thermal", "adapter_version": "1"},
                }

        return Adapter()

    def test_complete_explicit_contract_plans_with_a_qualified_plugin(self):
        result = plan_thermal_field_job(request(), solver_catalog=qualified_catalog())
        self.assertEqual(result["contract"], PLAN_CONTRACT)
        self.assertEqual(result["status"], "ready_for_execution")
        self.assertTrue(result["execution"]["permitted"])
        self.assertFalse(result["qualification"]["field_result_produced"])
        self.assertFalse(result["qualification"]["production_qualified"])
        self.assertEqual(result["resource_budget"]["requested_cells"], 30_000)
        self.assertEqual(len(result["plan_digest"]), 64)

    def test_plan_and_catalog_schemas_are_registered_and_valid(self):
        result = plan_thermal_field_job(request(), solver_catalog=qualified_catalog())
        plan_schema = json.loads((ROOT / "schemas" / "thermal-field-job-plan-v1.schema.json").read_text(encoding="utf-8"))
        request_schema = json.loads((ROOT / "schemas" / "thermal-field-job-request-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(plan_schema)
        Draft202012Validator(request_schema).validate(request())
        Draft202012Validator(plan_schema).validate(result)
        catalog = json.loads((ROOT / "schemas" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["schemas"][REQUEST_CONTRACT], "thermal-field-job-request-v1.schema.json")
        self.assertEqual(catalog["schemas"][PLAN_CONTRACT], "thermal-field-job-plan-v1.schema.json")
        self.assertEqual(catalog["schemas"]["spike/thermal-field-result/v1"], "thermal-field-result-v1.schema.json")

    def test_missing_geometry_contact_and_capability_evidence_fail_closed(self):
        value = request()
        value["geometry"] = {"qualified_geometry": False}
        catalog = qualified_catalog()
        catalog["fixture.qualified_thermal"]["capabilities"] = ["solid_conduction"]
        result = plan_thermal_field_job(value, solver_catalog=catalog)
        self.assertEqual(result["status"], "blocked")
        codes = {item["code"] for item in result["issues"]}
        self.assertTrue({"THERMAL_FIELD_GEOMETRY_EVIDENCE_REQUIRED", "THERMAL_FIELD_CONTACT_EVIDENCE_REQUIRED", "THERMAL_FIELD_SOLVER_CAPABILITY_MISSING"}.issubset(codes))

    def test_unqualified_or_automatic_solver_is_never_substituted(self):
        value = request()
        value["solver_selection"] = {"solver_id": "spike.lumped_thermal_network"}
        result = plan_thermal_field_job(value, solver_catalog={
            "spike.lumped_thermal_network": {"id": "spike.lumped_thermal_network", "state": "available", "model_status": "approximate", "actions": ["run"], "capabilities": ["solid_conduction"]},
        })
        self.assertEqual(result["status"], "blocked")
        self.assertIn("THERMAL_FIELD_SOLVER_NOT_QUALIFIED", {item["code"] for item in result["issues"]})
        automatic = request()
        automatic["solver_selection"] = {"solver_id": "auto"}
        with self.assertRaisesRegex(ThermalFieldJobError, "automatic fallback"):
            plan_thermal_field_job(automatic, solver_catalog=qualified_catalog())

    def test_budget_and_cancellation_are_enforced_without_partial_plan(self):
        value = request()
        value["resource_budget"]["max_cells"] = 10
        value["cancellation_enabled"] = False
        result = plan_thermal_field_job(value, solver_catalog=qualified_catalog())
        self.assertEqual(result["status"], "blocked")
        self.assertTrue({"THERMAL_FIELD_CELL_BUDGET_EXCEEDED", "THERMAL_FIELD_CANCELLATION_REQUIRED"}.issubset({item["code"] for item in result["issues"]}))
        with self.assertRaisesRegex(ThermalFieldJobError, "cancelled"):
            plan_thermal_field_job(request(), solver_catalog=qualified_catalog(), cancel_check=lambda: True)

    def test_unknown_physics_does_not_silently_drop_from_required_capabilities(self):
        value = copy.deepcopy(request())
        value["requested_physics"].append("invented_magic")
        with self.assertRaisesRegex(ThermalFieldJobError, "Unknown requested thermal physics"):
            plan_thermal_field_job(value, solver_catalog=qualified_catalog())

    def test_worker_route_uses_worker_owned_solver_catalog_and_fails_closed(self):
        value = request()
        value["solver_selection"] = {"solver_id": "spike.lumped_thermal_network"}
        response = handle({"id": "thermal-field-plan", "method": "plan_thermal_field_job", "params": {"request": value}})
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["status"], "blocked")
        self.assertIn("THERMAL_FIELD_SOLVER_NOT_QUALIFIED", {item["code"] for item in response["result"]["issues"]})

    def test_execution_requires_runtime_probe_and_normalizes_preview_plus_artifact_metadata(self):
        value = request()
        value["scenario"]["electrothermal"] = {"enabled": False}
        adapter = self._adapter(total_samples=10_000)
        result = execute_thermal_field_job(
            value, solver_catalog=qualified_catalog(), adapter_registry={"fixture.qualified_thermal": adapter},
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(adapter.calls, 1)
        temperature = result["fields"]["temperature_k"]
        self.assertEqual(temperature["preview_samples"], 1)
        self.assertEqual(temperature["total_samples"], 10_000)
        self.assertEqual(result["resource_usage"]["rendered_preview_samples"], 1)
        self.assertEqual(result["resource_usage"]["total_field_samples"], 10_000)
        self.assertTrue(result["qualification"]["production_qualified"])
        schema = json.loads((ROOT / "schemas" / "thermal-field-result-v1.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(result)

    def test_execution_rejects_failed_probe_and_never_exposes_partial_fields(self):
        value = request()
        value["scenario"]["electrothermal"] = {"enabled": False}
        adapter = self._adapter(probe_status="failed")
        result = execute_thermal_field_job(
            value, solver_catalog=qualified_catalog(), adapter_registry={"fixture.qualified_thermal": adapter},
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["fields"], {})
        self.assertEqual(adapter.calls, 0)
        self.assertEqual(result["issues"][0]["code"], "THERMAL_FIELD_RUNTIME_PROBE_FAILED")

    def test_electrothermal_iteration_is_bounded_and_requires_a_host_electrical_step(self):
        value = request()
        value["scenario"]["electrothermal"] = {"enabled": True, "max_iterations": 3, "temperature_tolerance_k": 0.1, "power_tolerance_w": 0.01}
        adapter = self._adapter()
        missing = execute_thermal_field_job(
            value, solver_catalog=qualified_catalog(), adapter_registry={"fixture.qualified_thermal": adapter},
        )
        self.assertEqual(missing["status"], "blocked")
        self.assertEqual(missing["issues"][0]["code"], "ELECTROTHERMAL_ELECTRICAL_ADAPTER_REQUIRED")
        adapter = self._adapter()
        result = execute_thermal_field_job(
            value, solver_catalog=qualified_catalog(), adapter_registry={"fixture.qualified_thermal": adapter},
            electrical_step=lambda temperatures, iteration: {"u1": 3.0},
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["electrothermal"]["status"], "converged")
        self.assertEqual(result["electrothermal"]["iterations"], 2)
        self.assertEqual(adapter.calls, 2)

    def test_cancellation_after_adapter_return_discards_partial_field_data(self):
        value = request()
        value["scenario"]["electrothermal"] = {"enabled": False}
        adapter = self._adapter()
        result = execute_thermal_field_job(
            value, solver_catalog=qualified_catalog(), adapter_registry={"fixture.qualified_thermal": adapter},
            cancel_check=lambda: adapter.calls >= 1,
        )
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["fields"], {})
        self.assertEqual(result["issues"][0]["code"], "THERMAL_FIELD_CANCELLED")


if __name__ == "__main__":
    unittest.main()
