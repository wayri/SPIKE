from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "thermal-relief-observed-topology-v1.schema.json"


def _attachment(index: int) -> dict:
    return {
        "attachment_id": ("a" if index == 0 else "b") * 64,
        "zone_id": f"zone-{index}", "filled_copper_id": f"fill-{index}",
        "source_fill_component_sha256": "c" * 64, "pad_edge_index": index,
        "boundary_start_fraction": 0.25, "boundary_end_fraction": 0.75,
        "boundary_center_mm": [1.0, 2.0], "outward_unit": [0.0, 1.0],
        "observed_normal_angle_deg": index * 90.0, "configured_angle_delta_deg": 0.0,
        "observed_boundary_width_mm": 0.5, "width_delta_mm": 0.0,
        "centerline_start_mm": [1.0, 2.0], "centerline_end_mm": [1.0, 2.3],
        "cross_sections": [
            {"offset_mm": offset, "start_tangent_mm": -0.25, "end_tangent_mm": 0.25, "width_mm": 0.5}
            for offset in (0.001, 0.15, 0.299, 0.301)
        ],
        "topology_state": "fixture_conforming_spoke_shaped_attachment",
    }


def _report(*, complete: bool = True) -> dict:
    records = [{
        "topology_id": "d" * 64, "profile": "four_cardinal_rectilinear_reservoir_v1",
        "pad_id": "pad-a", "component_id": "component-a", "source_zone_id": "zone-source-a",
        "layer_id": "F.Cu", "net_id": "VCC", "source_fill_group_id": "group-a",
        "source_fill_group_sha256": "e" * 64, "source_fill_component_count": 4,
        "effective_gap_mm": 0.3, "effective_width_mm": 0.5, "configured_angle_deg": 0.0,
        "attachment_count": 4, "attachments": [_attachment(index) for index in range(4)],
        "observation": "controlled_fixture_topology_matched",
    }] if complete else []
    return {
        "contract": "spike/thermal-relief-observed-topology/v1",
        "source": {"design_contract": "spike/design-ir/v2", "design_sha256": "f" * 64, "design_id": "design-a", "connection_contract": "spike/zone-pad-connection-evidence/v1", "connection_sha256": "1" * 64, "boundary_contact_contract": "spike/thermal-relief-boundary-contact-evidence/v1", "boundary_contact_sha256": "2" * 64},
        "records": records,
        "accounting": {"status": "complete" if complete else "no_candidates", "topology_record_count": len(records), "attachment_count": 4 if complete else 0, "all_controlled_candidates_accounted": True},
        "resources": {"maximum_records": 65536, "maximum_attachments": 262144, "maximum_component_vertices": 4096, "maximum_cross_sections": 1048576, "maximum_work_steps": 16777216, "maximum_serialized_bytes": 67108864, "actual_records": len(records), "actual_attachments": 4 if complete else 0, "actual_cross_sections": 16 if complete else 0, "actual_work_steps": 32, "actual_serialized_bytes": 2048, "cancellation_supported": True},
        "qualification": {"state": "controlled_source_fill_observed_spoke_topology_only", "controlled_fixture_observed_spoke_topology": complete, "general_kicad_thermal_spoke_topology_extracted": False, "thermal_spoke_topology_regenerated": False, "parametric_zone_refill_performed": False, "native_geometric_overlay_verified": False, "mesh_ready": False, "field_convergence_performed": False, "physics_ready": False, "solver_ready": False},
    }


class ThermalReliefObservedTopologySchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema)

    def test_manifest_and_complete_report_are_valid(self) -> None:
        manifest = json.loads((ROOT / "schemas" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schemas"]["spike/thermal-relief-observed-topology/v1"], "thermal-relief-observed-topology-v1.schema.json")
        self.validator.validate(_report())

    def test_no_candidates_report_is_valid_and_cannot_claim_controlled_topology(self) -> None:
        report = _report(complete=False)
        self.validator.validate(report)
        report["qualification"]["controlled_fixture_observed_spoke_topology"] = True
        with self.assertRaises(ValidationError):
            self.validator.validate(report)

    def test_promotion_claims_and_unknown_fields_are_rejected(self) -> None:
        for field in ("general_kicad_thermal_spoke_topology_extracted", "thermal_spoke_topology_regenerated", "parametric_zone_refill_performed", "native_geometric_overlay_verified", "mesh_ready", "field_convergence_performed", "physics_ready", "solver_ready"):
            report = _report()
            report["qualification"][field] = True
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.validator.validate(report)
        unknown = _report()
        unknown["records"][0]["spoke_count"] = 4
        with self.assertRaises(ValidationError):
            self.validator.validate(unknown)

    def test_profile_attachment_accounting_and_resources_fail_closed(self) -> None:
        cases = []
        profile = _report(); profile["records"][0]["profile"] = "generic"
        cases.append(profile)
        attachments = _report(); attachments["records"][0]["attachments"].pop()
        cases.append(attachments)
        accounting = _report(); accounting["accounting"]["status"] = "no_candidates"
        cases.append(accounting)
        no_candidates_count = _report(complete=False); no_candidates_count["accounting"]["attachment_count"] = 4
        cases.append(no_candidates_count)
        resources = _report(); resources["resources"]["maximum_attachments"] = 4
        cases.append(resources)
        for report in cases:
            with self.subTest(report=report), self.assertRaises(ValidationError):
                self.validator.validate(report)

    def test_digest_and_geometry_tampering_are_rejected(self) -> None:
        digest = _report(); digest["source"]["boundary_contact_sha256"] = "not-a-digest"
        geometry = _report(); geometry["records"][0]["attachments"][0]["boundary_center_mm"] = [1.0, 2.0, 3.0]
        for report in (digest, geometry):
            with self.subTest(report=report), self.assertRaises(ValidationError):
                self.validator.validate(report)

    def test_complete_status_requires_controlled_fixture_claim(self) -> None:
        report = copy.deepcopy(_report())
        report["qualification"]["controlled_fixture_observed_spoke_topology"] = False
        with self.assertRaises(ValidationError):
            self.validator.validate(report)


if __name__ == "__main__":
    unittest.main()
