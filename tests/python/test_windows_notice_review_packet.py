"""Focused contracts for the non-decisional Windows notice-review packet."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.build_windows_notice_review_packet import (
    NoticeReviewPacketError,
    build_notice_review_packet,
)


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "config" / "windows-component-inventory.json"
APPROVALS = ROOT / "licenses" / "windows-component-approvals.json"
SCHEMA = ROOT / "schemas" / "windows-notice-review-packet-v1.schema.json"


def _component(purl: str, identity: str, license_expression: str = "MIT") -> dict[str, str]:
    return {
        "purl": purl,
        "identity_sha256": identity,
        "scope": "bundled",
        "ecosystem": "python",
        "name": purl.split("/")[-1].split("@")[0],
        "version": purl.rsplit("@", 1)[1],
        "declared_license": license_expression,
    }


def _inputs(components: list[dict[str, str]], dispositions: list[str] | None = None) -> tuple[dict[str, object], dict[str, object]]:
    dispositions = dispositions or ["pending_review"] * len(components)
    return (
        {
            "contract": "spike/windows-component-inventory/v1",
            "platform": "windows-x64",
            "components": components,
        },
        {
            "contract": "spike/windows-component-approvals/v1",
            "platform": "windows-x64",
            "approvals": [
                {"purl": item["purl"], "identity_sha256": item["identity_sha256"], "disposition": disposition}
                for item, disposition in zip(components, dispositions, strict=True)
            ],
        },
    )


class WindowsNoticeReviewPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))

    def test_real_inventory_has_deterministic_exact_474_component_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "packet.json"
            first = build_notice_review_packet(INVENTORY, APPROVALS, output)
            first_bytes = output.read_bytes()
            second = build_notice_review_packet(INVENTORY, APPROVALS, output)
            self.assertEqual(first, second)
            self.assertEqual(first_bytes, output.read_bytes())
        self.validator.validate(first)
        inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
        self.assertEqual(len(first["components"]), 474)
        self.assertEqual([item["purl"] for item in first["components"]], [item["purl"] for item in inventory["components"]])
        self.assertEqual(first["summary"]["components"], 474)
        self.assertEqual(first["summary"]["pending_review_components"], 474)
        self.assertEqual(first["summary"]["needs_notice_text_components"], 474)
        self.assertEqual(first["summary"]["needs_legal_review_components"], 474)

    def test_small_fixture_has_unique_markers_and_spdx_shape_summary(self) -> None:
        components = [
            _component("pkg:pypi/valid@1.0", "a" * 64, "MIT"),
            _component("pkg:pypi/unresolved@1.0", "b" * 64, "LicenseRef-Local"),
            _component("pkg:pypi/invalid@1.0", "c" * 64, "MIT License"),
        ]
        inventory, approvals = _inputs(components)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory_path, approvals_path = root / "inventory.json", root / "approvals.json"
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            approvals_path.write_text(json.dumps(approvals), encoding="utf-8")
            packet = build_notice_review_packet(inventory_path, approvals_path)
        self.assertEqual([item["purl"] for item in packet["components"]], sorted(item["purl"] for item in components))
        markers = [item["proposed_notice_marker"] for item in packet["components"]]
        self.assertEqual(len(markers), len(set(markers)))
        self.assertEqual(packet["summary"]["invalid_spdx_declarations"], 1)
        self.assertEqual(packet["summary"]["unresolved_spdx_declarations"], 1)

    def test_packet_never_carries_approval_or_redistribution_claims(self) -> None:
        component = _component("pkg:pypi/example@1.0", "d" * 64)
        inventory, approvals = _inputs([component], ["approved"])
        approvals = copy.deepcopy(approvals)
        approvals["approvals"][0].update({
            "compliance_approved": True,
            "redistribution_approved": True,
            "approved_license_expression": "MIT",
        })
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory_path, approvals_path = root / "inventory.json", root / "approvals.json"
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            approvals_path.write_text(json.dumps(approvals), encoding="utf-8")
            packet = build_notice_review_packet(inventory_path, approvals_path)
        entry = packet["components"][0]
        self.assertEqual(entry["review_status"], "requires_manual_verification")
        self.assertTrue(entry["needs_notice_text"])
        self.assertTrue(entry["needs_legal_review"])
        prohibited = {"approved_license_expression", "compliance_approved", "redistribution_approved", "notice", "review"}
        self.assertTrue(prohibited.isdisjoint(entry))
        self.assertNotIn("THIRD_PARTY_NOTICES.md", json.dumps(packet, sort_keys=True))

    def test_rejects_missing_or_stale_approval_coverage(self) -> None:
        components = [_component("pkg:pypi/example@1.0", "e" * 64)]
        inventory, approvals = _inputs(components)
        approvals["approvals"][0]["identity_sha256"] = "f" * 64
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory_path, approvals_path = root / "inventory.json", root / "approvals.json"
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            approvals_path.write_text(json.dumps(approvals), encoding="utf-8")
            with self.assertRaises(NoticeReviewPacketError):
                build_notice_review_packet(inventory_path, approvals_path)


if __name__ == "__main__":
    unittest.main()
