from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.via_transition_geometry import AntipadSpec, build_via_transition_geometry
from python.spike_core.via_transition_mesh_quality import (
    ViaTransitionMeshQualityError,
    build_via_transition_mesh_quality,
    validate_via_transition_mesh_quality,
)
from python.spike_core.via_transition_native_handoff import build_native_via_transition_handoff


ROOT = Path(__file__).resolve().parents[2]


def geometry(via_type: str = "through", span: tuple[str, str] = ("F.Cu", "B.Cu")) -> dict:
    names = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    legacy = DesignIR(
        design_id=f"quality-{via_type}", name=f"quality-{via_type}", source_format="fixture",
        layers=[{"id": index, "name": name, "type": "copper", "thickness_mm": 0.035}
                for index, name in enumerate(names)],
        nets=[{"id": 1, "name": "SIG"}, {"id": 2, "name": "GND"}],
        vias=[{"id": "V1", "net_name": "SIG", "at": [2.0, 3.0], "diameter": 0.6,
               "drill": 0.3, "plating_mm": 0.025, "layers": list(span), "type": via_type}],
        zones=[{"id": f"GND:{name}", "net_name": "GND", "layer": name,
                "polygons": [[[-5.0, -5.0], [9.0, -5.0], [9.0, 11.0], [-5.0, 11.0]]]}
               for name in names], metadata={"source_sha256": "c" * 64},
    )
    design = DesignIRV2.from_v1(legacy)
    via = design.vias[0]
    reference_net = next(item.id for item in design.nets if item.name == "GND")
    reference_zone = next(item.id for item in design.zones
                          if item.net_id == reference_net and via.start_layer_id in item.layer_ids)
    return build_via_transition_geometry(
        design, via_id=via.id,
        antipads=[AntipadSpec(via.start_layer_id, 0.9, reference_net, reference_zone, 2.0,
                              "antipad:V1")],
    )


class ViaTransitionMeshQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(
            (ROOT / "schemas/pcb-via-transition-mesh-quality-v1.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(cls.schema)

    def test_report_is_deterministic_schema_valid_regenerated_and_geometry_only(self) -> None:
        source = geometry()
        first = build_via_transition_mesh_quality(source)
        self.assertEqual(first, build_via_transition_mesh_quality(source))
        Draft202012Validator(self.schema).validate(first)
        self.assertEqual(first, validate_via_transition_mesh_quality(first, source_geometry=source))
        self.assertEqual([item["radial_segments"] for item in first["levels"]], [8, 16, 32, 64])
        self.assertTrue(all(item["topology_audit_passed"] and item["native_admission_passed"]
                            for item in first["levels"]))
        self.assertEqual(first["qualification"], {
            "state": "geometry_domain_convergence_evidence",
            "geometry_convergence_passed": True,
            "physics_convergence_performed": False,
            "capacitance_ready": False,
            "si_ready": False,
            "solver_ready": False,
        })

    def test_all_supported_span_classes_pass_the_geometry_gate(self) -> None:
        cases = [("through", ("F.Cu", "B.Cu")), ("blind", ("B.Cu", "In2.Cu")),
                 ("buried", ("In1.Cu", "In2.Cu")), ("microvia", ("F.Cu", "In1.Cu"))]
        for via_type, span in cases:
            with self.subTest(via_type=via_type):
                report = build_via_transition_mesh_quality(geometry(via_type, span))
                self.assertTrue(report["convergence"]["passed"])

    def test_level_policy_and_numeric_inputs_fail_closed(self) -> None:
        source = geometry()
        for levels in ((8, 16, 32), (8, 16, 24, 48), (16, 32, 64, 256), (True, 16, 32, 64)):
            with self.subTest(levels=levels), self.assertRaises(ViaTransitionMeshQualityError):
                build_via_transition_mesh_quality(source, radial_levels=levels)
        for field in ("maximum_terminal_relative_error", "maximum_terminal_relative_change",
                      "maximum_terminal_normalized_radial_deviation"):
            with self.subTest(field=field), self.assertRaises(ViaTransitionMeshQualityError):
                build_via_transition_mesh_quality(source, **{field: "0.5"})
        with self.assertRaisesRegex(ViaTransitionMeshQualityError, "terminal domain convergence failed"):
            build_via_transition_mesh_quality(source, maximum_terminal_relative_error=1e-9)

    def test_mutated_or_physics_promoted_reports_fail_closed(self) -> None:
        source = geometry()
        report = build_via_transition_mesh_quality(source)
        promoted = copy.deepcopy(report)
        promoted["qualification"]["solver_ready"] = True
        with self.assertRaises(ValidationError):
            Draft202012Validator(self.schema).validate(promoted)
        with self.assertRaisesRegex(ViaTransitionMeshQualityError, "does not match"):
            validate_via_transition_mesh_quality(promoted, source_geometry=source)
        forged_levels = copy.deepcopy(report)
        forged_levels["policy"]["radial_levels"] = [16, 32, 64, 128]
        with self.assertRaises(ViaTransitionMeshQualityError):
            validate_via_transition_mesh_quality(forged_levels, source_geometry=source)

    def test_inconsistent_native_identity_cannot_be_counted_as_admitted(self) -> None:
        source = geometry()

        def forged(mesh: dict, *, source_geometry: dict) -> dict:
            result = build_native_via_transition_handoff(mesh, source_geometry=source_geometry)
            result["source"]["mesh_sha256"] = "0" * 64
            return result

        with patch("python.spike_core.via_transition_mesh_quality.build_native_via_transition_handoff",
                   side_effect=forged), self.assertRaisesRegex(ViaTransitionMeshQualityError, "quality=False"):
            build_via_transition_mesh_quality(source)


if __name__ == "__main__":
    unittest.main()
