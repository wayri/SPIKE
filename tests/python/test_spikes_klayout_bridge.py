# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from python.spikes.klayout_bridge import (
    KLayoutBridgeError,
    KLayoutExecutionError,
    KLayoutInspectionLimits,
    LAYOUT_INSPECTION_CONTRACT,
    _default_runner,
    inspect_layout,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_value(arguments: list[str], name: str) -> str:
    prefix = name + "="
    return next(item[len(prefix):] for item in arguments if item.startswith(prefix))


def _valid_report() -> dict[str, object]:
    return {
        "contract": LAYOUT_INSPECTION_CONTRACT,
        "status": "inspected",
        "engine": {"id": "klayout", "version": "0.29.fixture"},
        "model_status": "read_only_inspection",
        "units": {
            "dbu_um": 0.001,
            "integer_coordinates": "database_units",
            "physical_coordinates": "micrometres",
        },
        "summary": {
            "cell_count": 1,
            "top_cell_count": 1,
            "layer_count": 1,
            "defined_shape_count": 1,
            "hierarchy_edge_count": 0,
            "hierarchy_occurrence_count": 0,
        },
        "top_cells": [{
            "index": 0, "name": "TOP",
            "bbox_dbu": [0, 0, 1000, 2000],
            "bbox_um": [0.0, 0.0, 1.0, 2.0],
        }],
        "cells": [{
            "index": 0, "name": "TOP", "is_top": True,
            "direct_shape_count": 1,
            "direct_shapes": [{"layer_index": 0, "count": 1}],
            "children": [],
            "bbox_dbu": [0, 0, 1000, 2000],
            "bbox_um": [0.0, 0.0, 1.0, 2.0],
        }],
        "layers": [{
            "index": 0, "layer": 1, "datatype": 0, "name": "",
            "defined_shape_count": 1,
            "bbox_dbu": [0, 0, 1000, 2000],
            "bbox_um": [0.0, 0.0, 1.0, 2.0],
        }],
        "capabilities": {
            "layout_inspection": True,
            "layout_modification": False,
            "drc": False,
            "lvs": False,
            "pex": False,
        },
        "limitations": [
            "Shape counts cover definitions stored in cells, not flattened occurrence counts.",
            "This inspection does not perform DRC, LVS, parasitic extraction, or electrical validation.",
            "The KLayout child process is a process boundary, not a security sandbox.",
        ],
    }


class KLayoutBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix=".spikes-klayout-test-", dir=Path.cwd(),
        )
        self.root = Path(self.temporary.name)
        self.executable = self.root / "fixture-tool.bin"
        self.executable.write_bytes(b"fixture executable")
        self.layout = self.root / "fixture.gds"
        self.layout.write_bytes(b"fixture layout")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _runner(self, report: dict[str, object] | None = None):
        payload = report or _valid_report()

        def run(arguments, working_directory, timeout_s):
            arguments = list(arguments)
            self.assertEqual(arguments[0], str(self.executable.resolve()))
            self.assertEqual(arguments[1:4], ["-b", "-r", arguments[3]])
            self.assertEqual(Path(working_directory), Path(_runtime_value(arguments, "report_path")).parent)
            self.assertEqual(_runtime_value(arguments, "input_layout"), str(self.layout.resolve()))
            self.assertEqual(timeout_s, 12.0)
            Path(_runtime_value(arguments, "report_path")).write_text(
                json.dumps(payload), encoding="utf-8",
            )
            return subprocess.CompletedProcess(arguments, 0, b"", b"")

        return run

    def test_inspection_is_explicit_digest_bound_and_does_not_modify_layout(self):
        original = self.layout.read_bytes()
        result = inspect_layout(
            self.executable, self.layout, timeout_s=12.0, runner=self._runner(),
        )

        self.assertEqual(result["contract"], LAYOUT_INSPECTION_CONTRACT)
        self.assertEqual(result["units"]["dbu_um"], 0.001)
        self.assertEqual(result["top_cells"][0]["bbox_um"], [0.0, 0.0, 1.0, 2.0])
        self.assertEqual(result["provenance"]["executable_sha256"], _sha256(self.executable))
        self.assertEqual(result["provenance"]["layout_sha256"], _sha256(self.layout))
        probe = Path(result["provenance"]["probe_script_path"])
        self.assertEqual(result["provenance"]["probe_script_sha256"], _sha256(probe))
        self.assertEqual(self.layout.read_bytes(), original)
        self.assertFalse((self.root / "layout-report.json").exists())
        self.assertFalse(result["capabilities"]["pex"])
        self.assertIn("not a security sandbox", result["limitations"][-1])

    def test_missing_and_wrong_paths_are_rejected_before_process_start(self):
        called = False

        def runner(*_args):
            nonlocal called
            called = True
            raise AssertionError("must not run")

        with self.assertRaisesRegex(KLayoutBridgeError, "KLayout executable"):
            inspect_layout(self.root / "missing.exe", self.layout, runner=runner)
        with self.assertRaisesRegex(KLayoutBridgeError, "layout_path"):
            inspect_layout(self.executable, self.root / "missing.gds", runner=runner)
        unsupported = self.root / "layout.txt"
        unsupported.write_text("not a layout", encoding="ascii")
        with self.assertRaisesRegex(KLayoutBridgeError, "unsupported layout suffix"):
            inspect_layout(self.executable, unsupported, runner=runner)
        self.assertFalse(called)

    def test_timeout_and_limits_are_validated(self):
        for timeout in (0.0, -1.0, float("inf"), 301.0):
            with self.subTest(timeout=timeout), self.assertRaisesRegex(KLayoutBridgeError, "timeout_s"):
                inspect_layout(self.executable, self.layout, timeout_s=timeout, runner=self._runner())
        with self.assertRaisesRegex(KLayoutBridgeError, "max_cells"):
            KLayoutInspectionLimits(max_cells=0)
        with self.assertRaisesRegex(KLayoutBridgeError, "at most 1 GiB"):
            KLayoutInspectionLimits(max_input_bytes=1024**3 + 1)
        with self.assertRaisesRegex(KLayoutBridgeError, "input size limit"):
            inspect_layout(
                self.executable, self.layout,
                limits=KLayoutInspectionLimits(max_input_bytes=1),
                runner=self._runner(),
            )

    def test_timeout_has_stable_execution_error(self):
        def timeout(_arguments, _working_directory, timeout_s):
            raise subprocess.TimeoutExpired("klayout", timeout_s)

        with self.assertRaises(KLayoutExecutionError) as caught:
            inspect_layout(self.executable, self.layout, timeout_s=2.0, runner=timeout)
        self.assertEqual(caught.exception.code, "klayout_timeout")

    def test_default_runner_hard_bounds_combined_process_output(self):
        completed = _default_runner(
            [
                sys.executable, "-c",
                "import sys; sys.stdout.buffer.write(b'x' * 262144)",
            ],
            self.root,
            5.0,
            4096,
        )
        self.assertLessEqual(len(completed.stdout), 4097)
        self.assertLessEqual(len(completed.stderr), 4096)
        self.assertGreater(len(completed.stdout) + len(completed.stderr), 4096)

    def test_malformed_or_over_limit_reports_are_rejected(self):
        malformed = _valid_report()
        malformed["cells"][0]["bbox_um"] = [0.0, 0.0, 1.5, 2.0]
        with self.assertRaises(KLayoutExecutionError) as caught:
            inspect_layout(self.executable, self.layout, timeout_s=12.0, runner=self._runner(malformed))
        self.assertEqual(caught.exception.code, "invalid_probe_report")

        over_limit = _valid_report()
        over_limit["cells"][0]["direct_shape_count"] = 2
        over_limit["cells"][0]["direct_shapes"][0]["count"] = 2
        over_limit["layers"][0]["defined_shape_count"] = 2
        over_limit["summary"]["defined_shape_count"] = 2
        with self.assertRaises(KLayoutExecutionError) as caught:
            inspect_layout(
                self.executable, self.layout, timeout_s=12.0,
                limits=KLayoutInspectionLimits(max_shapes=1),
                runner=self._runner(over_limit),
            )
        self.assertEqual(caught.exception.code, "probe_limit_exceeded")

    def test_failed_probe_report_preserves_bounded_diagnostic(self):
        failed = {
            "contract": LAYOUT_INSPECTION_CONTRACT,
            "status": "failed",
            "error": {"code": "klayout_probe_failed", "detail": "bad layout"},
        }

        def runner(arguments, _working_directory, _timeout_s):
            Path(_runtime_value(list(arguments), "report_path")).write_text(
                json.dumps(failed), encoding="utf-8",
            )
            return subprocess.CompletedProcess(arguments, 1, b"", b"reader error")

        with self.assertRaises(KLayoutExecutionError) as caught:
            inspect_layout(self.executable, self.layout, runner=runner)
        self.assertEqual(caught.exception.code, "klayout_probe_failed")
        self.assertIn("bad layout", caught.exception.detail)


@unittest.skipUnless(
    os.environ.get("SPIKES_TEST_KLAYOUT", "").strip(),
    "set SPIKES_TEST_KLAYOUT to an explicit KLayout executable for integration coverage",
)
class KLayoutNativeIntegrationTests(unittest.TestCase):
    def test_native_hierarchical_gds_inspection(self):
        executable = Path(os.environ["SPIKES_TEST_KLAYOUT"]).resolve(strict=True)
        with tempfile.TemporaryDirectory(
            prefix=".spikes-klayout-native-", dir=Path.cwd(),
        ) as directory:
            root = Path(directory)
            layout_path = root / "hierarchical.gds"
            generator = root / "make_fixture.py"
            generator.write_text(
                "import pya\n"
                "layout = pya.Layout()\n"
                "layout.dbu = 0.001\n"
                "metal = layout.layer(1, 0)\n"
                "marker = layout.layer(7, 3)\n"
                "unit = layout.create_cell('UNIT')\n"
                "unit.shapes(metal).insert(pya.Box(0, 0, 10000, 5000))\n"
                "top = layout.create_cell('TOP')\n"
                "top.shapes(marker).insert(pya.Box(0, 0, 1000, 2000))\n"
                "top.insert(pya.CellInstArray(unit.cell_index(), pya.Trans(pya.Trans.R90, 20000, 30000)))\n"
                "layout.write(output_layout)\n",
                encoding="utf-8",
            )
            created = subprocess.run(
                [str(executable), "-b", "-r", str(generator), "-rd", f"output_layout={layout_path}"],
                cwd=root, capture_output=True, timeout=30.0, check=False, shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.assertEqual(
                created.returncode, 0,
                (created.stdout + created.stderr).decode("utf-8", errors="replace")[-4096:],
            )
            original_sha256 = _sha256(layout_path)

            result = inspect_layout(executable, layout_path)

            self.assertEqual(result["status"], "inspected")
            self.assertEqual(result["units"]["dbu_um"], 0.001)
            self.assertEqual(result["summary"], {
                "cell_count": 2,
                "top_cell_count": 1,
                "layer_count": 2,
                "defined_shape_count": 2,
                "hierarchy_edge_count": 1,
                "hierarchy_occurrence_count": 1,
            })
            top = next(item for item in result["cells"] if item["name"] == "TOP")
            child = top["children"][0]
            self.assertEqual(top["bbox_dbu"], [0, 0, 20000, 40000])
            self.assertEqual(top["bbox_um"], [0.0, 0.0, 20.0, 40.0])
            self.assertEqual(child["child_name"], "UNIT")
            self.assertEqual(child["bbox_dbu"], [15000, 30000, 20000, 40000])
            self.assertEqual(child["transform"]["rotation_degrees"], 90.0)
            self.assertEqual(child["transform"]["offset_dbu"], [20000, 30000])
            self.assertEqual(_sha256(layout_path), original_sha256)
            self.assertEqual(result["provenance"]["layout_sha256"], original_sha256)
            self.assertNotEqual(result["engine"]["version"], "unavailable")


if __name__ == "__main__":
    unittest.main()
