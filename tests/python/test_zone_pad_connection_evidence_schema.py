from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "zone-pad-connection-evidence-v1.schema.json"


def _report() -> dict:
    digest = "a" * 64
    return {
        "contract": "spike/zone-pad-connection-evidence/v1",
        "source": {
            "design_contract": "spike/design-ir/v2",
            "design_sha256": digest,
            "design_id": "design-a",
        },
        "records": [{
            "record_id": "pad-a|zone-a-filled|F.Cu",
            "pad_id": "pad-a",
            "component_id": "component-a",
            "pad_kind": "smd",
            "zone_id": "zone-a",
            "source_zone_id": "source-zone-a",
            "filled_copper_id": "zone-a-filled",
            "zone_geometry_state": "source_filled",
            "layer_id": "F.Cu",
            "net_id": "VCC",
            "pad_layer_mode": "inherit",
            "pad_mode": "inherit",
            "footprint_mode": "inherit",
            "zone_mode": "solid",
            "resolved_by": "zone_default",
            "resolved_mode": "solid",
            "through_hole_expansion": "not_applicable",
            "filled_copper_geometry_sha256": "b" * 64,
            "observation": "source_filled_copper_contact",
            "reason_code": "filled_polygon_intersection_observed",
            "topology_state": "not_regenerated",
        }],
        "accounting": {
            "status": "complete",
            "candidate_record_count": 1,
            "contact_record_count": 1,
            "no_contact_record_count": 0,
            "unsupported_record_count": 0,
            "all_candidate_connections_accounted": True,
        },
        "resources": {
            "maximum_pads": 65536,
            "maximum_source_filled_zones": 65536,
            "maximum_records": 262144,
            "maximum_work_steps": 16777216,
            "maximum_serialized_bytes": 134217728,
            "actual_pads": 1,
            "actual_source_filled_zones": 1,
            "actual_records": 1,
            "actual_work_steps": 1,
            "actual_serialized_bytes": 1024,
            "cancellation_supported": True,
        },
        "qualification": {
            "state": "source_filled_connection_evidence_only",
            "source_filled_copper_evidence_complete": True,
            "thermal_spoke_topology_regenerated": False,
            "parametric_zone_refill_performed": False,
            "native_geometric_overlay_verified": False,
            "field_convergence_performed": False,
            "physics_ready": False,
            "solver_ready": False,
        },
    }


class ZonePadConnectionEvidenceSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def test_contract_is_registered_and_valid_example_is_admitted(self) -> None:
        manifest = json.loads((ROOT / "schemas" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["schemas"]["spike/zone-pad-connection-evidence/v1"],
            "zone-pad-connection-evidence-v1.schema.json",
        )
        self.validator.validate(_report())

    def test_unknown_modes_unresolved_precedence_and_outline_geometry_fail_closed(self) -> None:
        cases = []
        unknown = _report()
        unknown["records"][0]["pad_mode"] = "unknown"
        cases.append(unknown)
        unresolved = _report()
        unresolved["records"][0]["resolved_mode"] = "inherit"
        cases.append(unresolved)
        bad_precedence = _report()
        bad_precedence["records"][0]["pad_mode"] = "none"
        cases.append(bad_precedence)
        outline = _report()
        outline["records"][0]["zone_geometry_state"] = "outline_fallback"
        cases.append(outline)
        for report in cases:
            with self.subTest(report=report["records"][0]), self.assertRaises(ValidationError):
                self.validator.validate(report)

    def test_observation_reason_pad_kind_and_through_hole_expansion_are_consistent(self) -> None:
        bad_reason = _report()
        bad_reason["records"][0]["reason_code"] = "filled_polygon_disjoint_observed"
        unknown_kind = _report()
        unknown_kind["records"][0]["pad_kind"] = "unknown"
        bad_tht = _report()
        bad_tht["records"][0]["pad_kind"] = "thru_hole"
        for report in (bad_reason, unknown_kind, bad_tht):
            with self.subTest(report=report["records"][0]), self.assertRaises(ValidationError):
                self.validator.validate(report)

        tht = _report()
        tht["records"][0]["pad_kind"] = "thru_hole"
        tht["records"][0]["through_hole_expansion"] = "expanded_on_canonical_copper_layer"
        self.validator.validate(tht)

    def test_resources_and_accounting_are_bounded_and_fail_closed(self) -> None:
        too_many = _report()
        too_many["resources"]["actual_records"] = 262145
        inconsistent_status = _report()
        inconsistent_status["accounting"]["unsupported_record_count"] = 1
        for report in (too_many, inconsistent_status):
            with self.subTest(report=report), self.assertRaises(ValidationError):
                self.validator.validate(report)

    def test_readiness_and_topology_claims_cannot_be_forged(self) -> None:
        fields = (
            "thermal_spoke_topology_regenerated",
            "parametric_zone_refill_performed",
            "native_geometric_overlay_verified",
            "field_convergence_performed",
            "physics_ready",
            "solver_ready",
        )
        for field in fields:
            promoted = copy.deepcopy(_report())
            promoted["qualification"][field] = True
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.validator.validate(promoted)
        regenerated = _report()
        regenerated["records"][0]["topology_state"] = "regenerated"
        with self.assertRaises(ValidationError):
            self.validator.validate(regenerated)


if __name__ == "__main__":
    unittest.main()
