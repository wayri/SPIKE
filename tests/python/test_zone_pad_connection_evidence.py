from __future__ import annotations

import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.design_ir_v2_schema import content_digest
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.zone_pad_connection_evidence import (
    MAX_SERIALIZED_BYTES,
    build_zone_pad_connection_evidence,
    validate_zone_pad_connection_evidence,
)


ROOT = Path(__file__).resolve().parents[2]


class ZonePadConnectionEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads((
            ROOT / "schemas" / "zone-pad-connection-evidence-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.schema_validator = Draft202012Validator(cls.schema)

    def design(self) -> DesignIRV2:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "zone-pad-evidence.kicad_pcb"
        path.write_text("""(kicad_pcb
          (version 20260101)
          (layers (0 "F.Cu" signal) (2 "B.Cu" signal))
          (net 1 "VCC")
          (zone (net 1) (net_name "VCC") (layer "F.Cu") (uuid "zone-a")
            (connect_pads yes (clearance 0.2))
            (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4))
            (polygon (pts (xy 0 0) (xy 5 0) (xy 5 5) (xy 0 5)))
            (filled_polygon (layer "F.Cu")
              (pts (xy 0 0) (xy 5 0) (xy 5 5) (xy 0 5))))
          (footprint "Fixture:Part" (layer "F.Cu") (at 1 1) (uuid "fp-a")
            (property "Reference" "J1")
            (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu")
              (net 1 "VCC") (uuid "pad-a")))
        )""", encoding="utf-8")
        return DesignIRV2.from_v1(import_kicad_design(str(path)))

    def test_digest_bound_source_filled_connection_evidence_is_schema_valid(self) -> None:
        design = self.design()
        report = build_zone_pad_connection_evidence(design)
        self.schema_validator.validate(report)
        self.assertEqual(
            report,
            validate_zone_pad_connection_evidence(report, source_geometry=design),
        )
        self.assertEqual(report["source"]["design_id"], design.design_id)
        self.assertEqual(report["source"]["design_sha256"], content_digest(design.to_dict()))
        self.assertGreaterEqual(len(report["records"]), 1)
        record = report["records"][0]
        self.assertEqual(record["zone_geometry_state"], "source_filled")
        self.assertEqual(record["resolved_by"], "zone_default")
        self.assertEqual(record["resolved_mode"], "solid")
        self.assertEqual(record["topology_state"], "not_regenerated")
        self.assertTrue(report["resources"]["cancellation_supported"])
        for field in (
            "thermal_spoke_topology_regenerated",
            "parametric_zone_refill_performed",
            "native_geometric_overlay_verified",
            "field_convergence_performed",
            "physics_ready",
            "solver_ready",
        ):
            self.assertFalse(report["qualification"][field])

    def test_unknown_identity_digest_mode_net_and_layer_tampering_fails_closed(self) -> None:
        design = self.design()
        report = build_zone_pad_connection_evidence(design)
        mutations = (
            ("stale digest", lambda item: item["source"].update(design_sha256="0" * 64)),
            ("unknown pad", lambda item: item["records"][0].update(pad_id="missing-pad")),
            ("unknown component", lambda item: item["records"][0].update(component_id="missing-component")),
            ("unknown zone", lambda item: item["records"][0].update(zone_id="missing-zone")),
            ("unknown source zone", lambda item: item["records"][0].update(source_zone_id="missing-source-zone")),
            ("unknown filled copper", lambda item: item["records"][0].update(filled_copper_id="missing-filled-copper")),
            ("mode tamper", lambda item: item["records"][0].update(pad_mode="solid")),
            ("net mismatch", lambda item: item["records"][0].update(net_id="OTHER")),
            ("layer mismatch", lambda item: item["records"][0].update(layer_id="B.Cu")),
        )
        for label, mutate in mutations:
            tampered = copy.deepcopy(report)
            mutate(tampered)
            with self.subTest(label=label), self.assertRaises(ValueError):
                validate_zone_pad_connection_evidence(tampered, source_geometry=design)

    def test_nonfilled_unknown_policy_and_invalid_pad_kind_sources_fail_closed(self) -> None:
        design = self.design()
        cases = []
        outline = design.to_dict()
        outline["zones"][0]["filled_copper_state"] = "outline_fallback"
        outline["zones"][0].update({
            "source_fill_group_id": "", "source_fill_group_sha256": "",
            "source_fill_component_ordinal": 0, "source_fill_component_count": 0,
            "source_fill_component_sha256": "", "source_fill_representation": "none",
            "source_fill_provenance_complete": False,
        })
        cases.append(DesignIRV2.from_dict(outline))

        unknown_policy = design.to_dict()
        unknown_policy["zones"][0]["zone_connection_default"] = "unknown"
        unknown_policy["zones"][0]["thermal_settings_valid"] = False
        cases.append(DesignIRV2.from_dict(unknown_policy))

        unknown_pad = design.to_dict()
        unknown_pad["pads"][0]["pad_kind"] = "unknown"
        cases.append(DesignIRV2.from_dict(unknown_pad))

        for index, candidate in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValueError):
                build_zone_pad_connection_evidence(candidate)

    def test_tampered_through_hole_expansion_and_forged_readiness_are_rejected(self) -> None:
        design = self.design()
        report = build_zone_pad_connection_evidence(design)
        invalid_tht = copy.deepcopy(report)
        invalid_tht["records"][0]["pad_kind"] = "thru_hole"
        with self.assertRaises(ValidationError):
            self.schema_validator.validate(invalid_tht)
        with self.assertRaises(ValueError):
            validate_zone_pad_connection_evidence(invalid_tht, source_geometry=design)

        promoted = copy.deepcopy(report)
        promoted["qualification"]["solver_ready"] = True
        with self.assertRaises(ValidationError):
            self.schema_validator.validate(promoted)
        with self.assertRaises(ValueError):
            validate_zone_pad_connection_evidence(promoted, source_geometry=design)

    def test_cancellation_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "cancelled"):
            build_zone_pad_connection_evidence(
                self.design(), cancel_check=lambda: True,
            )

    def test_marble_scale_limit_is_128_mib_and_still_fails_closed_above_it(self) -> None:
        """The resource gate admits Marble-scale source fills, but not unbounded input."""
        self.assertEqual(MAX_SERIALIZED_BYTES, 128 * 1024 * 1024)
        with patch(
            "python.spike_core.zone_pad_connection_evidence._canonical_digest_and_size",
            return_value=("a" * 64, MAX_SERIALIZED_BYTES + 1),
        ):
            with self.assertRaisesRegex(ValueError, "128 MiB"):
                build_zone_pad_connection_evidence(self.design())


if __name__ == "__main__":
    unittest.main()
