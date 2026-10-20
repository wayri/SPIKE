# SPDX-License-Identifier: Apache-2.0
"""Execute and validate bounded PI01-S01 owned-pad numerical evidence."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STAGE = "PI01-S01"
MODULES = ("tests.python.test_hybrid_owned_copper", "tests.python.test_hybrid_drilled_roundrect",
           "tests.python.test_custom_pad_drill")
SOURCES = (
    "scripts/parity_owned_pad_gate.py",
    "scripts/check_ebrake_owned_dc.py", "python/spike_core/convergence.py",
    "python/spike_core/cli.py",
    "python/spike_core/hybrid_drilled_roundrect.py",
    "python/spike_core/hybrid_mesh.py", "python/spike_core/hybrid_owned_copper.py",
    "python/spike_core/hybrid_dc_solver.py", "python/spike_core/dc_result_utils.py",
    "python/spike_core/quasistatic_copper_area.py", "python/spike_core/contracts.py",
    "python/spike_core/kicad_importer.py", "python/core/board_parser.py",
    "tests/python/test_hybrid_owned_copper.py", "tests/python/test_hybrid_drilled_roundrect.py",
    "tests/python/test_custom_pad_drill.py",
    "app/public/demo/ebrake1.kicad_pcb", "docs/OWNED_DRILLED_PAD_DC.md",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def suite():
    return unittest.defaultTestLoader.loadTestsFromNames(MODULES)


def names(tests):
    return sorted(name for item in tests for name in
                  (names(item) if isinstance(item, unittest.TestSuite) else [item.id()]))


def _bound(root, name, expected):
    if not isinstance(name, str):
        raise ValueError("Owned-pad evidence path required")
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or digest(path) != expected:
        raise ValueError("Owned-pad evidence is stale or foreign")
    return path


def validate_receipt(receipt, root=ROOT):
    if (receipt.get("contract") != "spike/owned-pad-stage-evidence/v1"
            or receipt.get("stage_id") != STAGE or receipt.get("status") != "passed"
            or receipt.get("production_qualified") is not False):
        raise ValueError("Owned-pad stage identity, execution or scope differs")
    before, after = receipt.get("sources_before"), receipt.get("sources_after")
    if not isinstance(before, dict) or set(before) != set(SOURCES) or before != after:
        raise ValueError("Owned-pad source coverage differs or drifted during execution")
    for name, value in before.items():
        _bound(root, name, value)
    expected = names(suite())
    result = receipt.get("tests", {})
    if (not expected or any("_FailedTest" in name for name in expected)
            or result.get("names") != expected or result.get("run") != len(expected)
            or any(result.get(k) != [] for k in ("failures", "errors", "skipped",
                                                "expected_failures", "unexpected_successes"))):
        raise ValueError("Owned-pad execution is incomplete or failed")
    log = _bound(root, receipt.get("log"), receipt.get("log_sha256")).read_text(encoding="utf-8")
    if f"Ran {len(expected)} tests" not in log or not log.rstrip().endswith("OK"):
        raise ValueError("Owned-pad execution log is incomplete")
    validate_board(receipt.get("board_artifacts"), root)


def validate_board(artifacts, root=ROOT):
    from scripts.check_ebrake_owned_dc import SOURCES as board_sources
    required = {"report.json", "request.json", "cli-result.json", "cli.log", "convergence.json"}
    if not isinstance(artifacts, dict) or set(artifacts) != required:
        raise ValueError("Owned-pad stage requires the actual full-board execution")
    paths = {key: _bound(root, item.get("path"), item.get("sha256"))
             for key, item in artifacts.items()}
    report = json.loads(paths["report.json"].read_text(encoding="utf-8"))
    before = report.get("sources_before", {})
    if (report.get("contract") != "spike/ebrake-owned-dc-audit/v1"
            or report.get("cli_completed") is not True or report.get("cli_exit_code") != 0
            or report.get("sources_unchanged") is not True
            or report.get("production_qualified") is not False
            or set(before) != set(board_sources) or before != report.get("sources_after")):
        raise ValueError("Actual EBrake owned-mode execution failed or drifted")
    for name, value in before.items():
        _bound(root, name, value)
    actual_board = digest(root / "app/public/demo/ebrake1.kicad_pcb")
    if report.get("board_sha256") != actual_board or report.get("board_sha256_after") != actual_board:
        raise ValueError("Actual EBrake board changed")
    cli = json.loads(paths["cli-result.json"].read_text(encoding="utf-8"))
    study = json.loads(paths["convergence.json"].read_text(encoding="utf-8"))
    if (cli.get("status") != "completed" or cli.get("model_status") != "approximate"
            or study.get("can_sign_off") is not report.get("can_sign_off")
            or study.get("status") != report.get("convergence_status")
            or study.get("comparisons") != report.get("comparisons")):
        raise ValueError("Actual EBrake raw results and summary differ")
    levels = study.get("levels", [])
    if ([row.get("target_size_mm") for row in levels] != [2, 1, .5, .25]
            or any(row.get("status") != "completed" for row in levels)
            or study.get("thresholds") != {"max_load_voltage_drop_v": .03,
                "total_copper_loss_w": .05, "effective_path_resistance_ohm": .05,
                "p95_current_density_a_mm2": .1}
            or study.get("absolute_thresholds") != {"max_load_voltage_drop_v": 5e-5}):
        raise ValueError("Actual EBrake mesh execution or unchanged convergence gates differ")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--board-dir", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.log):
        if not path.resolve().is_relative_to(ROOT) or path.exists():
            parser.error("Select fresh repository output paths")
        path.parent.mkdir(parents=True, exist_ok=True)
    before = {name: digest(ROOT / name) for name in SOURCES}
    artifacts = {name: {"path": (args.board_dir / name).resolve().relative_to(ROOT).as_posix(),
                        "sha256": digest(args.board_dir / name)}
                 for name in ("report.json", "request.json", "cli-result.json", "cli.log", "convergence.json")}
    validate_board(artifacts)
    tests = suite()
    expected = names(tests)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
    after = {name: digest(ROOT / name) for name in SOURCES}
    args.log.write_text(stream.getvalue(), encoding="utf-8")
    receipt = {"contract": "spike/owned-pad-stage-evidence/v1", "stage_id": STAGE,
               "status": "passed" if result.wasSuccessful() and not result.skipped and before == after else "failed",
               "production_qualified": False, "sources_before": before, "sources_after": after,
               "board_artifacts": artifacts,
               "tests": {"names": expected, "run": result.testsRun,
                         **{key: [test.id() for test, _ in getattr(result, attr)] for key, attr in
                            (("failures", "failures"), ("errors", "errors"), ("skipped", "skipped"),
                             ("expected_failures", "expectedFailures"))},
                         "unexpected_successes": [test.id() for test in result.unexpectedSuccesses]},
               "log": args.log.resolve().relative_to(ROOT).as_posix(), "log_sha256": digest(args.log)}
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    validate_receipt(receipt)
    print(json.dumps({"stage_id": STAGE, "tests": result.testsRun, "status": "passed"}))


if __name__ == "__main__":
    main()
