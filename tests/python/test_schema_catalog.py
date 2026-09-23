"""Regression tests for SPIKE's public JSON contract catalog."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = ROOT / "schemas"


class SchemaCatalogTests(unittest.TestCase):
    def test_every_public_schema_is_valid_json(self) -> None:
        schemas = sorted(SCHEMA_ROOT.glob("*.schema.json"))
        self.assertGreaterEqual(len(schemas), 20)
        for schema in schemas:
            with self.subTest(schema=schema.name):
                document = json.loads(schema.read_text(encoding="utf-8"))
                self.assertIsInstance(document, dict)
                self.assertEqual(document.get("$schema"), "https://json-schema.org/draft/2020-12/schema")

    def test_cad_neutral_foundation_schemas_are_published(self) -> None:
        expected = {
            "assembly-package-shapes-v1.schema.json",
            "assembly-placement-policy-v1.schema.json",
            "assembly-ir-v1.schema.json",
            "design-ir-v2.schema.json",
            "import-report-v1.schema.json",
            "geometry-index-v1.schema.json",
            "model-index-v1.schema.json",
            "spike-project-package-v3.schema.json",
            "workspace-state-v1.schema.json",
        }
        self.assertTrue(expected.issubset({path.name for path in SCHEMA_ROOT.glob("*.schema.json")}))

    def test_wave1_packaged_acceptance_schemas_are_published(self) -> None:
        expected = {
            "wave1-packaged-acceptance-v1.schema.json",
            "wave1-human-acceptance-evidence-v1.schema.json",
            "wave1-packaged-acceptance-v2.schema.json",
            "wave1-human-acceptance-evidence-v2.schema.json",
            "windows-installer-manifest-v2.schema.json",
            "windows-release-sbom-v1.schema.json",
            "windows-release-provenance-v1.schema.json",
            "wave1-clean-machine-harness-v1.schema.json",
            "wave1-clean-machine-harness-v2.schema.json",
        }
        published = {path.name for path in SCHEMA_ROOT.glob("*.schema.json")}
        self.assertTrue(expected.issubset(published))
        report = json.loads((SCHEMA_ROOT / "wave1-packaged-acceptance-v1.schema.json").read_text(encoding="utf-8"))
        evidence = json.loads((SCHEMA_ROOT / "wave1-human-acceptance-evidence-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(report["properties"]["contract"]["const"], "spike/wave1-packaged-acceptance/v1")
        self.assertEqual(evidence["properties"]["contract"]["const"], "spike/wave1-human-acceptance-evidence/v1")

    def test_signed_candidate_schemas_publish_v2_contracts(self) -> None:
        installer = json.loads((SCHEMA_ROOT / "windows-installer-manifest-v2.schema.json").read_text(encoding="utf-8"))
        report = json.loads((SCHEMA_ROOT / "wave1-packaged-acceptance-v2.schema.json").read_text(encoding="utf-8"))
        evidence = json.loads((SCHEMA_ROOT / "wave1-human-acceptance-evidence-v2.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(installer["properties"]["contract"]["const"], "spike/windows-installer-manifest/v2")
        self.assertEqual(report["properties"]["contract"]["const"], "spike/wave1-packaged-acceptance/v2")
        self.assertEqual(evidence["properties"]["contract"]["const"], "spike/wave1-human-acceptance-evidence/v2")
        harness = json.loads((SCHEMA_ROOT / "wave1-clean-machine-harness-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(harness["properties"]["contract"]["const"], "spike/wave1-clean-machine-harness/v1")
        harness_v2 = json.loads((SCHEMA_ROOT / "wave1-clean-machine-harness-v2.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(harness_v2["properties"]["contract"]["const"], "spike/wave1-clean-machine-harness/v2")

    def test_windows_release_provenance_schemas_publish_v1_contracts(self) -> None:
        sbom = json.loads((SCHEMA_ROOT / "windows-release-sbom-v1.schema.json").read_text(encoding="utf-8"))
        provenance = json.loads((SCHEMA_ROOT / "windows-release-provenance-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(sbom["properties"]["contract"]["const"], "spike/windows-release-sbom/v1")
        self.assertEqual(provenance["properties"]["contract"]["const"], "spike/windows-release-provenance/v1")

    def test_windows_component_inventory_and_approval_schemas_are_published(self) -> None:
        inventory = json.loads((SCHEMA_ROOT / "windows-component-inventory-v1.schema.json").read_text(encoding="utf-8"))
        approvals = json.loads((SCHEMA_ROOT / "windows-component-approvals-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(inventory["properties"]["contract"]["const"], "spike/windows-component-inventory/v1")
        self.assertEqual(approvals["properties"]["contract"]["const"], "spike/windows-component-approvals/v1")

    def test_windows_notice_review_packet_schema_is_registered(self) -> None:
        catalog = json.loads((SCHEMA_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["contract"], "spike/schema-catalog/v1")
        self.assertEqual(
            catalog["schemas"]["spike/windows-notice-review-packet/v1"],
            "windows-notice-review-packet-v1.schema.json",
        )
        self.assertEqual(catalog["schemas"]["spike/wave1-clean-machine-harness/v2"], "wave1-clean-machine-harness-v2.schema.json")
        packet = json.loads((SCHEMA_ROOT / "windows-notice-review-packet-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(packet["properties"]["contract"]["const"], "spike/windows-notice-review-packet/v1")

    def test_windows_notice_evidence_index_schema_is_registered(self) -> None:
        catalog = json.loads((SCHEMA_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["schemas"]["spike/windows-notice-evidence-index/v1"], "windows-notice-evidence-index-v1.schema.json")
        schema = json.loads((SCHEMA_ROOT / "windows-notice-evidence-index-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["contract"]["const"], "spike/windows-notice-evidence-index/v1")

    def test_via_transition_geometry_schema_is_registered(self) -> None:
        catalog = json.loads((SCHEMA_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            catalog["schemas"]["spike/pcb-via-transition-geometry/v1"],
            "pcb-via-transition-geometry-v1.schema.json",
        )
        self.assertEqual(
            catalog["schemas"]["spike/pcb-via-transition-mesh/v1"],
            "pcb-via-transition-mesh-v1.schema.json",
        )
        self.assertEqual(
            catalog["schemas"]["spike/native-via-transition-handoff/v1"],
            "native-via-transition-handoff-v1.schema.json",
        )
        self.assertEqual(
            catalog["schemas"]["spike/pcb-via-transition-mesh-quality/v1"],
            "pcb-via-transition-mesh-quality-v1.schema.json",
        )
        self.assertEqual(
            catalog["schemas"]["spike/pcb-reference-plane-antipad-geometry/v1"],
            "pcb-reference-plane-antipad-geometry-v1.schema.json",
        )
        self.assertEqual(catalog["schemas"]["spike/pcb-reference-plane-antipad-geometry/v2"],
                         "pcb-reference-plane-antipad-geometry-v2.schema.json")
        self.assertEqual(catalog["schemas"]["spike/pcb-reference-plane-antipad-geometry/v3"],
                         "pcb-reference-plane-antipad-geometry-v3.schema.json")
        self.assertEqual(
            catalog["schemas"]["spike/pcb-reference-plane-antipad-mesh/v1"],
            "pcb-reference-plane-antipad-mesh-v1.schema.json",
        )
        self.assertEqual(
            catalog["schemas"]["spike/pcb-reference-plane-antipad-mesh/v2"],
            "pcb-reference-plane-antipad-mesh-v2.schema.json",
        )
        self.assertEqual(
            catalog["schemas"]["spike/native-reference-plane-antipad-handoff/v1"],
            "native-reference-plane-antipad-handoff-v1.schema.json",
        )
        self.assertEqual(
            catalog["schemas"]["spike/native-reference-plane-antipad-handoff/v2"],
            "native-reference-plane-antipad-handoff-v2.schema.json",
            "pcb-reference-plane-mesh-ownership-v1.schema.json",
        )
        self.assertEqual(catalog["schemas"]["spike/pcb-reference-plane-antipad-mesh-quality/v1"],
                         "pcb-reference-plane-antipad-mesh-quality-v1.schema.json")
        self.assertEqual(catalog["schemas"]["spike/pcb-reference-plane-antipad-mesh-quality/v2"],
                         "pcb-reference-plane-antipad-mesh-quality-v2.schema.json")
        handoff = json.loads((SCHEMA_ROOT / "native-via-transition-handoff-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(handoff["properties"]["contract"]["const"], "spike/native-via-transition-handoff/v1")
        quality = json.loads((SCHEMA_ROOT / "pcb-via-transition-mesh-quality-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(quality["properties"]["contract"]["const"], "spike/pcb-via-transition-mesh-quality/v1")
        full_plane_handoff = json.loads((SCHEMA_ROOT / "native-reference-plane-antipad-handoff-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(full_plane_handoff["properties"]["contract"]["const"], "spike/native-reference-plane-antipad-handoff/v1")

    def test_package_manifest_registers_the_model_index_contract(self) -> None:
        schema = json.loads((SCHEMA_ROOT / "spike-project-package-v3.schema.json").read_text(encoding="utf-8"))
        schemas = schema["properties"]["schemas"]
        self.assertIn("model_index", schemas["required"])
        self.assertEqual(schemas["properties"]["model_index"]["const"], "spike/model-index/v1")

    def test_package_manifest_registers_the_geometry_index_contract(self) -> None:
        schema = json.loads((SCHEMA_ROOT / "spike-project-package-v3.schema.json").read_text(encoding="utf-8"))
        schemas = schema["properties"]["schemas"]
        self.assertIn("geometry_index", schemas["required"])
        self.assertEqual(schemas["properties"]["geometry_index"]["const"], "spike/geometry-index/v1")

    def test_package_manifest_registers_the_assembly_placement_policy_contract(self) -> None:
        schema = json.loads((SCHEMA_ROOT / "spike-project-package-v3.schema.json").read_text(encoding="utf-8"))
        schemas = schema["properties"]["schemas"]
        self.assertIn("assembly_placement_policy", schemas["required"])
        self.assertEqual(
            schemas["properties"]["assembly_placement_policy"]["const"],
            "spike/assembly-placement-policy/v1",
        )

    def test_package_manifest_registers_the_assembly_package_shapes_contract(self) -> None:
        schema = json.loads((SCHEMA_ROOT / "spike-project-package-v3.schema.json").read_text(encoding="utf-8"))
        schemas = schema["properties"]["schemas"]
        self.assertIn("assembly_package_shapes", schemas["required"])
        self.assertEqual(
            schemas["properties"]["assembly_package_shapes"]["const"],
            "spike/assembly-package-shapes/v1",
        )


if __name__ == "__main__":
    unittest.main()
