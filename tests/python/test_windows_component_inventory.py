"""Contracts for the generated Windows component inventory and review overlay."""

from __future__ import annotations

import copy
import hashlib
import json
import unittest
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.prepare_windows_component_approvals import prepare_approval_overlay
from scripts.verify_windows_component_approvals import (
    ComponentApprovalError,
    verify_component_approvals,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
INVENTORY_PATH = ROOT / "config" / "windows-component-inventory.json"
SHA256 = "a" * 64


def load(name: str) -> dict[str, object]:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def approval(disposition: str = "approved") -> dict[str, object]:
    payload: dict[str, object] = {
        "purl": "pkg:pypi/example@1.2.3",
        "identity_sha256": SHA256,
        "disposition": disposition,
    }
    if disposition == "approved":
        payload.update({
            "approved_license_expression": "MIT",
            "compliance_approved": True,
            "redistribution_approved": True,
            "notice": {"status": "included", "file": "THIRD_PARTY_NOTICES.md", "sha256": SHA256, "marker": "example"},
            "review": {"ticket": "SPIKE-123", "reviewer": "release@example.invalid", "reviewed_at": "2026-08-27T00:00:00Z"},
        })
    return payload


def approvals() -> dict[str, object]:
    return {
        "contract": "spike/windows-component-approvals/v1",
        "platform": "windows-x64",
        "inventory_sha256": SHA256,
        "notices_sha256": SHA256,
        "approvals": [approval()],
    }


class WindowsComponentInventorySchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory_schema = load("windows-component-inventory-v1.schema.json")
        cls.approvals_schema = load("windows-component-approvals-v1.schema.json")
        Draft202012Validator.check_schema(cls.inventory_schema)
        Draft202012Validator.check_schema(cls.approvals_schema)
        cls.inventory_validator = Draft202012Validator(cls.inventory_schema)
        cls.approvals_validator = Draft202012Validator(cls.approvals_schema)

    def test_generated_inventory_validates_against_the_public_schema(self) -> None:
        self.inventory_validator.validate(json.loads(INVENTORY_PATH.read_text(encoding="utf-8")))

    def test_generated_inventory_is_stably_ordered_unique_and_identity_hashed(self) -> None:
        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        components = inventory["components"]
        purls = [item["purl"] for item in components]
        self.assertEqual(purls, sorted(purls))
        self.assertEqual(len(purls), len(set(purls)))
        for component in components:
            identity = {key: component[key] for key in sorted(component) if key != "identity_sha256"}
            encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            self.assertEqual(component["identity_sha256"], hashlib.sha256(encoded).hexdigest())

    def test_inventory_cannot_contain_approval_claims(self) -> None:
        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        prohibited = {"approved_license_expression", "redistribution_approved", "notice", "review", "disposition"}
        for component in inventory["components"]:
            self.assertTrue(prohibited.isdisjoint(component))
        tampered = copy.deepcopy(inventory)
        tampered["components"][0]["redistribution_approved"] = True
        self.assertFalse(self.inventory_validator.is_valid(tampered))

    def test_approval_overlay_has_exact_key_and_digest_contract(self) -> None:
        self.approvals_validator.validate(approvals())
        for mutate in (
            lambda item: item.pop("purl"),
            lambda item: item.__setitem__("identity_sha256", "not-a-digest"),
            lambda item: item.__setitem__("extra", True),
        ):
            with self.subTest(mutate=mutate):
                payload = approvals()
                mutate(payload["approvals"][0])
                self.assertFalse(self.approvals_validator.is_valid(payload))

    def test_approved_overlay_requires_complete_approval_evidence(self) -> None:
        for mutation in (
            lambda item: item.pop("approved_license_expression"),
            lambda item: item.__setitem__("redistribution_approved", False),
            lambda item: item["notice"].pop("marker"),
            lambda item: item["review"].pop("reviewed_at"),
        ):
            with self.subTest(mutation=mutation):
                payload = approvals()
                mutation(payload["approvals"][0])
                self.assertFalse(self.approvals_validator.is_valid(payload))

    def test_pending_and_excluded_overlays_need_only_the_identity_key(self) -> None:
        for disposition in ("pending_review", "excluded"):
            with self.subTest(disposition=disposition):
                payload = approvals()
                payload["approvals"] = [approval(disposition)]
                self.approvals_validator.validate(payload)

    def test_current_overlay_tracks_every_component_but_grants_nothing(self) -> None:
        overlay_path = ROOT / "licenses" / "windows-component-approvals.json"
        overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        self.approvals_validator.validate(overlay)
        self.assertEqual(
            [item["purl"] for item in overlay["approvals"]],
            [item["purl"] for item in inventory["components"]],
        )
        self.assertTrue(all(item["disposition"] == "pending_review" for item in overlay["approvals"]))
        with self.assertRaises(ComponentApprovalError):
            verify_component_approvals(
                INVENTORY_PATH, overlay_path, ROOT / "THIRD_PARTY_NOTICES.md", ROOT,
            )

    def test_preparer_invalidates_a_decision_when_component_identity_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory_path = root / "inventory.json"
            notices_path = root / "notices.md"
            existing_path = root / "existing.json"
            output_path = root / "output.json"
            inventory_path.write_text(json.dumps({
                "contract": "spike/windows-component-inventory/v1",
                "components": [{"purl": "pkg:pypi/example@1.0", "identity_sha256": "b" * 64}],
            }), encoding="utf-8")
            notices_path.write_text("# Notices\n", encoding="utf-8")
            existing_path.write_text(json.dumps({
                "contract": "spike/windows-component-approvals/v1",
                "approvals": [{"purl": "pkg:pypi/example@1.0", "identity_sha256": "a" * 64,
                               "disposition": "approved"}],
            }), encoding="utf-8")
            prepared = prepare_approval_overlay(
                inventory_path, notices_path, output_path, existing_path,
            )
            self.assertEqual(prepared["approvals"][0]["disposition"], "pending_review")
            self.assertEqual(prepared["approvals"][0]["identity_sha256"], "b" * 64)

    def test_verifier_accepts_only_complete_digest_bound_human_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            notices = root / "THIRD_PARTY_NOTICES.md"
            notices.write_text("# Notices\n\n## example\nMIT\n", encoding="utf-8")
            identity = "c" * 64
            inventory = root / "inventory.json"
            inventory.write_text(json.dumps({
                "contract": "spike/windows-component-inventory/v1", "platform": "windows-x64",
                "components": [{"purl": "pkg:pypi/example@1.0", "identity_sha256": identity,
                                "scope": "bundled", "declared_license": "MIT"}],
            }), encoding="utf-8")
            overlay = root / "approvals.json"
            overlay.write_text(json.dumps({
                "contract": "spike/windows-component-approvals/v1", "platform": "windows-x64",
                "inventory_sha256": hashlib.sha256(inventory.read_bytes()).hexdigest(),
                "notices_sha256": hashlib.sha256(notices.read_bytes()).hexdigest(),
                "approvals": [{
                    "purl": "pkg:pypi/example@1.0", "identity_sha256": identity,
                    "disposition": "approved", "approved_license_expression": "MIT",
                    "compliance_approved": True, "redistribution_approved": True,
                    "notice": {"status": "included", "file": notices.name,
                               "sha256": hashlib.sha256(notices.read_bytes()).hexdigest(),
                               "marker": "## example"},
                    "review": {"ticket": "LEGAL-1", "reviewer": "Reviewer",
                               "reviewed_at": "2026-08-27T00:00:00Z"},
                }],
            }), encoding="utf-8")
            result = verify_component_approvals(inventory, overlay, notices, root)
            self.assertEqual(result["status"], "passed")
            self.assertFalse(result["production_qualified"])


if __name__ == "__main__":
    unittest.main()
