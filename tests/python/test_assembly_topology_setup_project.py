"""Manifest-bound exact topology setup update regressions."""

from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.project_package import read_project, write_spike_package
from python.spike_core.service_project_handlers import handle_project_request
from tests.python import test_assembly_package_shapes as package_shape_fixtures


class AssemblyTopologySetupProjectTests(unittest.TestCase):
    def test_setup_update_preserves_exact_shapes_and_artifacts_and_fails_closed(self):
        assembly, models, index, model_artifacts, shape_artifacts = package_shape_fixtures.AssemblyPackageShapeTests().fixture()
        design = DesignIRV2.from_v1(DesignIR(
            design_id="topology-setup", name="Topology setup", source_format="neutral",
            layers=[{"id": 0, "name": "F.Cu"}], metadata={"source_sha256": "8" * 64},
        ))
        payload = {
            "project": {"id": "topology-setup", "name": "Topology setup"},
            "design_ir": design.to_dict(),
            "assembly_ir": assembly,
            "models": models,
            "assembly_package_shapes": index,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "topology.spike"
            initial_manifest = write_spike_package(
                path, payload, model_artifacts=model_artifacts,
                package_shape_artifacts=shape_artifacts,
            )
            before = read_project(path, include_members=True)
            requested_constraints = [deepcopy(index["constraints"][0])]
            response = handle_project_request(
                "update_assembly_topology_setup_in_project",
                {
                    "project_path": str(path),
                    "expected_manifest_payload_sha256": initial_manifest["manifest_payload_sha256"],
                    "constraints": requested_constraints,
                    "thermal_contact_bindings": deepcopy(index["thermal_contact_bindings"]),
                    "electrical_bond_bindings": deepcopy(index["electrical_bond_bindings"]),
                },
                request_id="topology-update", application_version="test",
            )
            self.assertTrue(response["ok"], response)
            self.assertTrue(response["result"]["shape_artifacts_unchanged"])
            self.assertFalse(response["result"]["solver_ready"])
            after = read_project(path, include_members=True)
            self.assertEqual(after.payload["assembly_package_shapes"]["shapes"], before.payload["assembly_package_shapes"]["shapes"])
            self.assertEqual(after.payload["assembly_package_shapes"]["constraints"], requested_constraints)
            for name in before.members:
                if name.startswith("geometry/package-shapes/"):
                    self.assertEqual(after.members[name], before.members[name])
            self.assertEqual(after.payload["audit"][-1]["event"], "assembly_topology_setup_updated")

            stale = handle_project_request(
                "update_assembly_topology_setup_in_project",
                {
                    "project_path": str(path),
                    "expected_manifest_payload_sha256": initial_manifest["manifest_payload_sha256"],
                    "constraints": [], "thermal_contact_bindings": [], "electrical_bond_bindings": [],
                },
                request_id="stale", application_version="test",
            )
            self.assertFalse(stale["ok"])
            self.assertIn("changed since it was verified", str(stale))

            invalid_binding = [{
                "assembly_entity_id": "contact",
                "endpoint_a": "legacy-a",
                "endpoint_b": "legacy-b",
            }]
            rejected = handle_project_request(
                "update_assembly_topology_setup_in_project",
                {
                    "project_path": str(path),
                    "expected_manifest_payload_sha256": after.manifest["manifest_payload_sha256"],
                    "constraints": requested_constraints,
                    "thermal_contact_bindings": invalid_binding,
                    "electrical_bond_bindings": deepcopy(index["electrical_bond_bindings"]),
                },
                request_id="legacy", application_version="test",
            )
            self.assertFalse(rejected["ok"])
            self.assertIn("must contain exactly", str(rejected))
            unchanged = read_project(path, include_members=True)
            self.assertEqual(unchanged.manifest["manifest_payload_sha256"], after.manifest["manifest_payload_sha256"])

            forbidden = handle_project_request(
                "update_assembly_topology_setup_in_project",
                {
                    "project_path": str(path),
                    "expected_manifest_payload_sha256": after.manifest["manifest_payload_sha256"],
                    "constraints": [], "thermal_contact_bindings": [], "electrical_bond_bindings": [],
                    "shapes": [],
                },
                request_id="forbidden", application_version="test",
            )
            self.assertFalse(forbidden["ok"])
            self.assertIn("three setup arrays", str(forbidden))

    def test_exact_concentric_constraint_applies_transactionally(self):
        assembly, models, index, model_artifacts, shape_artifacts = package_shape_fixtures.AssemblyPackageShapeTests().fixture()
        design = DesignIRV2.from_v1(DesignIR(
            design_id="geometric-snap", name="Geometric snap", source_format="neutral",
            layers=[{"id": 0, "name": "F.Cu"}], metadata={"source_sha256": "9" * 64},
        ))
        payload = {"project": {"id": "snap"}, "design_ir": design.to_dict(), "assembly_ir": assembly, "models": models, "assembly_package_shapes": index}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snap.spike"
            manifest = write_spike_package(path, payload, model_artifacts=model_artifacts, package_shape_artifacts=shape_artifacts)
            response = handle_project_request("apply_assembly_geometric_constraint_in_project", {
                "project_path": str(path),
                "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                "constraint_id": "concentric", "moving_part_id": "part-b",
            }, request_id="snap", application_version="test")
            self.assertTrue(response["ok"], response)
            self.assertEqual(response["result"]["geometry_source"], "exact_brep_descriptor")
            self.assertTrue(response["result"]["shape_artifacts_unchanged"])
            self.assertFalse(response["result"]["solver_ready"])
            reopened = read_project(path, include_members=True)
            part = next(item for item in reopened.payload["assembly_ir"]["parts"] if item["id"] == "part-b")
            self.assertAlmostEqual(part["frame"]["transform"][3], -10.0)
            self.assertEqual(reopened.payload["audit"][-1]["event"], "assembly_geometric_constraint_applied")
            self.assertFalse(reopened.payload["audit"][-1]["contacts_or_bonds_inferred"])
            stale = handle_project_request("apply_assembly_geometric_constraint_in_project", {
                "project_path": str(path),
                "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                "constraint_id": "concentric", "moving_part_id": "part-b",
            }, request_id="stale-snap", application_version="test")
            self.assertFalse(stale["ok"])
            self.assertIn("changed since it was verified", str(stale))


if __name__ == "__main__":
    unittest.main()
