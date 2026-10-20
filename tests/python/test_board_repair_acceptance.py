# SPDX-License-Identifier: Apache-2.0
"""Prevent skip, omitted case, or stale-source promotion in the board repair audit."""
import copy
from pathlib import Path
import tempfile
import unittest

from scripts.verify_board_repair_acceptance import (
    FIXTURE_NAMES, acceptance_passed, fixture_evidence, plan, source_snapshot,
)


class BoardRepairAcceptanceTests(unittest.TestCase):
    def test_original_fixture_requires_exact_four_tests_and_no_skips(self):
        lines = [f"{name.rsplit('.',1)[1]} ({name}) ... ok" for name in sorted(FIXTURE_NAMES)]
        log = "\n".join(lines) + "\nRan 4 tests in 1.0s\n\nOK\n"
        self.assertTrue(fixture_evidence(log, 0)["acceptance_passed"])
        for value, code in ((log, 1), (log.replace("... ok", "... skipped 'native missing'", 1), 0),
                (log.replace("Ran 4", "Ran 3"), 0), (log.replace(lines[0], ""), 0),
                (log.replace("\nOK\n", "\nOK (skipped=1)\n"), 0),
                (log.replace("test_board_extracts_expected_geometry", "different_test"), 0)):
            with self.subTest(value=value, code=code):
                self.assertFalse(fixture_evidence(value, code)["acceptance_passed"])

    def test_required_cases_native_and_source_identity_cannot_be_omitted(self):
        cases = [{"name": name, "required": True, "acceptance_passed": True} for name in (
            "native-contact-audit", "original-ebrake-fixture", "ebrake-owned-dc", "marble-refined-rt0")]
        source = {"input.py": "original"}
        runtime = {"native_available": True, "native_sha256": "original"}
        self.assertTrue(acceptance_passed(cases, source, source, runtime, runtime))
        failed = copy.deepcopy(cases)
        failed[1]["acceptance_passed"] = False
        for selected, before, after, first, last in (
                (cases[:-1], source, source, runtime, runtime),
                (cases + [cases[0]], source, source, runtime, runtime),
                (failed, source, source, runtime, runtime),
                (cases, {}, {}, runtime, runtime),
                (cases, source, {"input.py": "changed"}, runtime, runtime),
                (cases, source, source, runtime, dict(runtime, native_sha256="changed")),
                (cases, source, source, {"native_available": False}, {"native_available": False})):
            self.assertFalse(acceptance_passed(selected, before, after, first, last))

    def test_plan_preserves_original_tests_and_previous_marble_resource_envelope(self):
        rows = {row["name"]: row for row in plan(Path("unused-plan-output"))}
        fixture = rows["original-ebrake-fixture"]["command"]
        self.assertEqual(fixture[1:], ["-m", "unittest", "tests.python.test_kicad_fixture", "-v"])
        marble = rows["marble-refined-rt0"]["command"]
        self.assertEqual(marble[marble.index("--sizes")+1:marble.index("--max-unknowns")], [".5", ".25", ".125"])
        for key, expected in (("--max-unknowns", "250000"), ("--max-triangles", "250000"), ("--interior-edge-factor", ".25")):
            self.assertEqual(marble[marble.index(key)+1], expected)
        self.assertFalse(rows["public-board-diagnostics"]["required"])

    def test_source_guard_detects_new_helper_and_changed_content(self):
        from scripts.verify_board_repair_acceptance import BOARDS, SCRIPTS
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in [*SCRIPTS, *(value[0] for value in BOARDS.values())]:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("initial", encoding="utf-8")
            before = source_snapshot(root)
            helper = root / "python/spike_core/new_helper.py"
            helper.parent.mkdir(parents=True, exist_ok=True)
            helper.write_text("new", encoding="utf-8")
            after = source_snapshot(root)
            self.assertNotEqual(before, after)
            helper.write_text("changed", encoding="utf-8")
            self.assertNotEqual(after, source_snapshot(root))


if __name__ == "__main__":
    unittest.main()
