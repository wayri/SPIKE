from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.thermal_relief_boundary_contact import (
    build_thermal_relief_boundary_contact_evidence,
    validate_thermal_relief_boundary_contact_evidence,
)
from python.spike_core.zone_pad_connection_evidence import build_zone_pad_connection_evidence


ROOT = Path(__file__).resolve().parents[2]


class ThermalReliefBoundaryContactTests(unittest.TestCase):
    def design(self, *, pad_x: float = 0.0) -> DesignIRV2:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "thermal-boundary.kicad_pcb"
        path.write_text(f"""(kicad_pcb
          (version 20260101)
          (layers (0 "F.Cu" signal))
          (net 1 "VCC")
          (zone (net 1) (net_name "VCC") (layer "F.Cu") (uuid "zone-a")
            (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.5))
            (polygon (pts (xy -4 -4) (xy 4 -4) (xy 4 4) (xy -4 4)))
            (filled_polygon (layer "F.Cu")
              (pts (xy -0.25 -3) (xy 0.25 -3) (xy 0.25 3) (xy -0.25 3))))
          (footprint "Fixture:Part" (layer "F.Cu") (at {pad_x} 0) (uuid "fp-a")
            (property "Reference" "J1")
            (pad "1" smd rect (at 0 0) (size 2 2) (layers "F.Cu")
              (net 1 "VCC") (uuid "pad-a"))))""", encoding="utf-8")
        return DesignIRV2.from_v1(import_kicad_design(str(path)))

    def build(self, design: DesignIRV2):
        connection = build_zone_pad_connection_evidence(design)
        return connection, build_thermal_relief_boundary_contact_evidence(design, connection)

    def test_partial_polygonal_boundary_contact_is_digest_bound_and_schema_valid(self):
        design = self.design()
        connection, report = self.build(design)
        schema = json.loads((
            ROOT / "schemas" / "thermal-relief-boundary-contact-evidence-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(report)
        self.assertEqual(report, validate_thermal_relief_boundary_contact_evidence(
            report, source_geometry=design, connection_evidence=connection,
        ))
        self.assertEqual(report["accounting"]["record_count"], 1)
        record = report["records"][0]
        self.assertEqual(record["observation"], "boundary_contact_extracted")
        self.assertEqual(record["boundary_contact_kind"], "partial")
        self.assertEqual(len(record["boundary_intervals"]), 2)
        self.assertTrue(all(item["length_mm"] > 0 for item in record["boundary_intervals"]))
        self.assertFalse(report["qualification"]["thermal_spoke_topology_extracted"])

    def test_disjoint_source_fill_is_accounted_without_boundary_intervals(self):
        design = self.design(pad_x=8.0)
        _, report = self.build(design)
        record = report["records"][0]
        self.assertEqual(record["observation"], "no_source_filled_contact")
        self.assertEqual(record["boundary_contact_kind"], "none")
        self.assertEqual(record["boundary_intervals"], [])
        self.assertEqual(report["accounting"]["status"], "complete")

    def test_incomplete_source_fill_provenance_is_explicitly_unsupported(self):
        design = self.design()
        payload = design.to_dict()
        payload["zones"][0].update({
            "source_fill_group_id": "", "source_fill_group_sha256": "",
            "source_fill_component_ordinal": 0, "source_fill_component_count": 0,
            "source_fill_component_sha256": "", "source_fill_representation": "none",
            "source_fill_provenance_complete": False,
        })
        incomplete = DesignIRV2.from_dict(payload)
        _, report = self.build(incomplete)
        self.assertEqual(report["accounting"]["status"], "unsupported")
        self.assertEqual(report["records"][0]["reason_code"], "source_fill_provenance_incomplete")
        self.assertFalse(report["qualification"]["boundary_contact_evidence_complete"])

    def test_tampering_and_forged_spoke_or_solver_claims_fail(self):
        design = self.design()
        connection, report = self.build(design)
        for field in ("thermal_spoke_topology_extracted", "solver_ready"):
            tampered = copy.deepcopy(report)
            tampered["qualification"][field] = True
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_thermal_relief_boundary_contact_evidence(
                    tampered, source_geometry=design, connection_evidence=connection,
                )
        stale = copy.deepcopy(report)
        stale["records"][0]["pad_id"] = "other-pad"
        with self.assertRaises(ValueError):
            validate_thermal_relief_boundary_contact_evidence(
                stale, source_geometry=design, connection_evidence=connection,
            )

    def test_cancellation_fails_without_partial_report(self):
        design = self.design()
        connection = build_zone_pad_connection_evidence(design)
        with self.assertRaisesRegex(ValueError, "cancelled"):
            build_thermal_relief_boundary_contact_evidence(
                design, connection, cancel_check=lambda: True,
            )


if __name__ == "__main__":
    unittest.main()
