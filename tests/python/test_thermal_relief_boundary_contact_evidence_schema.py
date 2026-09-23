from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "thermal-relief-boundary-contact-evidence-v1.schema.json"


def _report() -> dict:
    digest = "a" * 64
    return {
        "contract": "spike/thermal-relief-boundary-contact-evidence/v1",
        "source": {
            "design_contract": "spike/design-ir/v2",
            "design_sha256": digest,
            "design_id": "design-a",
            "connection_contract": "spike/zone-pad-connection-evidence/v1",
            "connection_sha256": "b" * 64,
        },
        "records": [{
            "record_id": "connection-a|boundary",
            "connection_evidence_id": "connection-a",
            "pad_id": "pad-a",
            "zone_id": "zone-a",
            "filled_copper_id": "zone-a-filled",
            "layer_id": "F.Cu",
            "net_id": "VCC",
            "resolved_mode": "thermal",
            "source_fill_group_id": "fill-group-a",
            "source_fill_group_sha256": "c" * 64,
            "source_fill_component_sha256": "d" * 64,
            "observation": "boundary_contact_extracted",
            "reason_code": "polygonal_pad_boundary_observed",
            "boundary_contact_kind": "partial",
            "boundary_intervals": [{
                "edge_index": 0,
                "start_fraction": 0.0,
                "end_fraction": 0.5,
                "start_mm": [1.0, 2.0],
                "end_mm": [1.5, 2.0],
                "length_mm": 0.5,
            }],
        }],
        "accounting": {
            "status": "complete",
            "record_count": 1,
            "extracted_record_count": 1,
            "no_contact_record_count": 0,
            "unsupported_record_count": 0,
            "all_thermal_candidates_accounted": True,
        },
        "resources": {
            "maximum_records": 262144,
            "maximum_intervals": 1048576,
            "maximum_work_steps": 16777216,
            "maximum_serialized_bytes": 67108864,
            "actual_records": 1,
            "actual_intervals": 1,
            "actual_work_steps": 1,
            "actual_serialized_bytes": 1024,
            "cancellation_supported": True,
        },
        "qualification": {
            "state": "source_filled_pad_boundary_contact_only",
            "boundary_contact_evidence_complete": True,
            "thermal_spoke_topology_extracted": False,
            "thermal_spoke_topology_regenerated": False,
            "parametric_zone_refill_performed": False,
            "mesh_ready": False,
            "field_convergence_performed": False,
            "physics_ready": False,
            "solver_ready": False,
        },
    }


class ThermalReliefBoundaryContactEvidenceSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def test_contract_is_registered_and_valid_report_is_admitted(self) -> None:
        manifest = json.loads((ROOT / "schemas" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["schemas"]["spike/thermal-relief-boundary-contact-evidence/v1"],
            "thermal-relief-boundary-contact-evidence-v1.schema.json",
        )
        self.validator.validate(_report())

    def test_promotion_and_spoke_claims_are_rejected(self) -> None:
        for field in (
            "thermal_spoke_topology_extracted",
            "thermal_spoke_topology_regenerated",
            "parametric_zone_refill_performed",
            "mesh_ready",
            "field_convergence_performed",
            "physics_ready",
            "solver_ready",
        ):
            report = _report()
            report["qualification"][field] = True
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.validator.validate(report)

    def test_source_record_and_interval_tampering_are_rejected(self) -> None:
        cases = []
        wrong_connection = _report()
        wrong_connection["source"]["connection_contract"] = "spike/other/v1"
        cases.append(wrong_connection)
        nonthermal = _report()
        nonthermal["records"][0]["resolved_mode"] = "solid"
        cases.append(nonthermal)
        no_boundary_interval = _report()
        no_boundary_interval["records"][0]["boundary_intervals"] = []
        cases.append(no_boundary_interval)
        unsupported_with_geometry = _report()
        unsupported_with_geometry["records"][0].update({
            "observation": "unsupported",
            "reason_code": "pad_boundary_unsupported",
            "boundary_contact_kind": "unsupported",
        })
        cases.append(unsupported_with_geometry)
        for report in cases:
            with self.subTest(report=report), self.assertRaises(ValidationError):
                self.validator.validate(report)

    def test_accounting_resources_and_unknown_fields_fail_closed(self) -> None:
        cases = []
        status = _report()
        status["accounting"]["unsupported_record_count"] = 1
        cases.append(status)
        resource_limit = _report()
        resource_limit["resources"]["actual_intervals"] = 1048577
        cases.append(resource_limit)
        resource_constant = _report()
        resource_constant["resources"]["maximum_records"] = 1
        cases.append(resource_constant)
        unknown = _report()
        unknown["records"][0]["spoke_count"] = 4
        cases.append(unknown)
        for report in cases:
            with self.subTest(report=report), self.assertRaises(ValidationError):
                self.validator.validate(report)

    def test_unsupported_status_requires_incomplete_evidence(self) -> None:
        report = _report()
        report["accounting"].update({"status": "unsupported", "unsupported_record_count": 1})
        report["qualification"]["boundary_contact_evidence_complete"] = False
        self.validator.validate(report)
        complete = copy.deepcopy(report)
        complete["qualification"]["boundary_contact_evidence_complete"] = True
        with self.assertRaises(ValidationError):
            self.validator.validate(complete)


if __name__ == "__main__":
    unittest.main()
