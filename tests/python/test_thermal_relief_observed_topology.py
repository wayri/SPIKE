from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.thermal_relief_boundary_contact import (
    build_thermal_relief_boundary_contact_evidence,
)
from python.spike_core.thermal_relief_observed_topology import (
    build_thermal_relief_observed_topology,
    validate_thermal_relief_observed_topology,
)
from python.spike_core.zone_pad_connection_evidence import (
    build_zone_pad_connection_evidence,
)


class ThermalReliefObservedTopologyTests(unittest.TestCase):
    COMPONENTS = (
        "(filled_polygon (layer \"F.Cu\") (pts (xy -0.75 -3) (xy 0.75 -3) (xy 0.75 -1.3) (xy 0.25 -1.3) (xy 0.25 -0.85) (xy -0.25 -0.85) (xy -0.25 -1.3) (xy -0.75 -1.3)))",
        "(filled_polygon (layer \"F.Cu\") (pts (xy 3 -0.75) (xy 3 0.75) (xy 1.3 0.75) (xy 1.3 0.25) (xy 0.85 0.25) (xy 0.85 -0.25) (xy 1.3 -0.25) (xy 1.3 -0.75)))",
        "(filled_polygon (layer \"F.Cu\") (pts (xy 0.75 3) (xy -0.75 3) (xy -0.75 1.3) (xy -0.25 1.3) (xy -0.25 0.85) (xy 0.25 0.85) (xy 0.25 1.3) (xy 0.75 1.3)))",
        "(filled_polygon (layer \"F.Cu\") (pts (xy -3 0.75) (xy -3 -0.75) (xy -1.3 -0.75) (xy -1.3 -0.25) (xy -0.85 -0.25) (xy -0.85 0.25) (xy -1.3 0.25) (xy -1.3 0.75)))",
    )

    def design(
        self, *, width: float = 0.5, angle: float = 0.0,
        pad_x: float = 0.0, component_order=(0, 1, 2, 3),
    ) -> DesignIRV2:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "observed-topology.kicad_pcb"
        polygons = "\n".join(self.COMPONENTS[index] for index in component_order)
        path.write_text(f"""(kicad_pcb
          (version 20260101)
          (layers (0 "F.Cu" signal))
          (net 1 "VCC")
          (zone (net 1) (net_name "VCC") (layer "F.Cu") (uuid "zone-profile")
            (fill yes (thermal_gap 0.3) (thermal_bridge_width {width}))
            (polygon (pts (xy -4 -4) (xy 4 -4) (xy 4 4) (xy -4 4)))
            {polygons})
          (footprint "Fixture:Part" (layer "F.Cu") (at {pad_x} 0) (uuid "fp-a")
            (property "Reference" "J1")
            (pad "1" smd rect (at 0 0) (size 2 2) (layers "F.Cu")
              (net 1 "VCC") (uuid "pad-a") (thermal_bridge_angle {angle}))))""",
            encoding="utf-8",
        )
        return DesignIRV2.from_v1(import_kicad_design(str(path)))

    def dependencies(self, design):
        connection = build_zone_pad_connection_evidence(design)
        boundary = build_thermal_relief_boundary_contact_evidence(design, connection)
        return connection, boundary

    def build(self, design):
        connection, boundary = self.dependencies(design)
        return connection, boundary, build_thermal_relief_observed_topology(
            design, connection, boundary,
        )

    def test_four_cardinal_width_gap_and_reservoir_profile_is_admitted(self):
        design = self.design()
        connection, boundary, report = self.build(design)
        self.assertEqual(report, validate_thermal_relief_observed_topology(
            report, source_geometry=design, connection_evidence=connection,
            boundary_contact_evidence=boundary,
        ))
        self.assertEqual(report["accounting"], {
            "status": "complete", "topology_record_count": 1,
            "attachment_count": 4, "all_controlled_candidates_accounted": True,
        })
        record = report["records"][0]
        self.assertEqual(record["attachment_count"], 4)
        self.assertEqual(
            [item["observed_normal_angle_deg"] for item in record["attachments"]],
            [0.0, 90.0, 180.0, 270.0],
        )
        self.assertTrue(all(len(item["cross_sections"]) == 4 for item in record["attachments"]))
        self.assertTrue(report["qualification"]["controlled_fixture_observed_spoke_topology"])
        self.assertFalse(report["qualification"]["general_kicad_thermal_spoke_topology_extracted"])

    def test_component_source_order_does_not_change_observed_attachments(self):
        first = self.build(self.design())[2]["records"][0]
        swapped = self.build(self.design(component_order=(3, 1, 0, 2)))[2]["records"][0]
        fields = lambda record: [(
            item["source_fill_component_sha256"], item["observed_normal_angle_deg"],
            item["observed_boundary_width_mm"], item["topology_state"],
        ) for item in record["attachments"]]
        self.assertEqual(fields(first), fields(swapped))

    def test_width_angle_and_incomplete_profile_fail_closed(self):
        cases = (
            ("width", self.design(width=0.4)),
            ("angle", self.design(angle=45)),
            ("cardinality", self.design(component_order=(0, 1, 2))),
        )
        for label, design in cases:
            connection, boundary = self.dependencies(design)
            with self.subTest(label=label), self.assertRaises(ValueError):
                build_thermal_relief_observed_topology(design, connection, boundary)

    def test_disjoint_design_has_no_controlled_candidate(self):
        _, _, report = self.build(self.design(pad_x=8.0))
        self.assertEqual(report["accounting"]["status"], "no_candidates")
        self.assertEqual(report["records"], [])
        self.assertFalse(report["qualification"]["controlled_fixture_observed_spoke_topology"])

    def test_tampering_promotion_and_cancellation_fail_closed(self):
        design = self.design()
        connection, boundary, report = self.build(design)
        promoted = copy.deepcopy(report)
        promoted["qualification"]["solver_ready"] = True
        with self.assertRaises(ValueError):
            validate_thermal_relief_observed_topology(
                promoted, source_geometry=design, connection_evidence=connection,
                boundary_contact_evidence=boundary,
            )
        tampered = copy.deepcopy(report)
        tampered["records"][0]["attachments"][0]["observed_boundary_width_mm"] += 0.1
        with self.assertRaises(ValueError):
            validate_thermal_relief_observed_topology(
                tampered, source_geometry=design, connection_evidence=connection,
                boundary_contact_evidence=boundary,
            )
        with self.assertRaisesRegex(ValueError, "cancelled"):
            build_thermal_relief_observed_topology(
                design, connection, boundary, cancel_check=lambda: True,
            )


if __name__ == "__main__":
    unittest.main()
