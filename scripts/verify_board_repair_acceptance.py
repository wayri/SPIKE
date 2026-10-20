# SPDX-License-Identifier: Apache-2.0
"""Replay unchanged EBrake/Marble checks with raw artifacts and source/native guards."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_board_terminal_contacts import BOARDS, digest

FIXTURE_CLASS = "tests.python.test_kicad_fixture.KicadFixtureTests."
FIXTURE_NAMES = {FIXTURE_CLASS + name for name in (
    "test_board_extracts_expected_geometry", "test_hybrid_net_runs_through_native_peec",
    "test_routed_dc_mesh_convergence_signs_off", "test_routed_dc_path_returns_an_approximate_result")}
SCRIPTS = ("scripts/verify_board_repair_acceptance.py", "scripts/audit_board_terminal_contacts.py",
    "scripts/check_ebrake_owned_dc.py", "scripts/check_board_pisi_readiness.py",
    "scripts/audit_peec_rt0_refinement.py", "tests/python/test_kicad_fixture.py")


def source_snapshot(root=ROOT):
    paths = {root / path for path in SCRIPTS}
    paths.update(root / spec[0] for spec in BOARDS.values())
    # Package-wide coverage catches newly added helpers and changed file sets.
    for directory, suffixes in (("python/spike_core", {".py"}), ("python/core", {".py"}),
            ("python/bindings", {".cpp", ".hpp", ".h"}), ("src/peec", {".cpp", ".hpp", ".h"})):
        paths.update(path for path in (root / directory).rglob("*")
                     if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts)
    return {path.relative_to(root).as_posix(): digest(path) for path in sorted(paths)}


def runtime_descriptor():
    from python.spike_core.peec_plugin import native
    path = Path(native.__file__).resolve() if native is not None else None
    versions = {}
    for name in ("numpy", "scipy", "shapely"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {"python_executable": str(Path(sys.executable).resolve()), "python_version": sys.version,
        "dependency_versions": versions, "native_available": native is not None,
        "native_path": str(path) if path else None, "native_sha256": digest(path) if path else None}


def plan(folder):
    marble = ROOT / BOARDS["marble"][0]
    return [
        {"name": "native-contact-audit", "kind": "contact", "required": True,
         "command": [sys.executable, "scripts/audit_board_terminal_contacts.py", "--output", str(folder / "contacts.json")]},
        {"name": "original-ebrake-fixture", "kind": "fixture", "required": True,
         "command": [sys.executable, "-m", "unittest", "tests.python.test_kicad_fixture", "-v"]},
        {"name": "ebrake-owned-dc", "kind": "owned", "required": True,
         "command": [sys.executable, "scripts/check_ebrake_owned_dc.py", "--output-dir", str(folder / "ebrake-owned")]},
        {"name": "marble-refined-rt0", "kind": "rt0", "required": True,
         "command": [sys.executable, "scripts/audit_peec_rt0_refinement.py", "--board", str(marble),
             "--sizes", ".5", ".25", ".125", "--max-unknowns", "250000", "--max-triangles", "250000",
             "--interior-edge-factor", ".25", "--output", str(folder / "marble-refined-rt0.json")]},
        {"name": "public-board-diagnostics", "kind": "public", "required": False,
         "command": [sys.executable, "scripts/check_board_pisi_readiness.py", "--output-dir", str(folder / "public-boards")]},
    ]


def fixture_evidence(log, returncode):
    entries = re.findall(r"^\w+ \(([^)]+)\) \.\.\. (.+)$", log, re.MULTILINE)
    counts = re.findall(r"^Ran (\d+) tests? in .+$", log, re.MULTILINE)
    complete = (len(entries) == 4 and {name for name, _ in entries} == FIXTURE_NAMES
                and counts == ["4"])
    passed = (returncode == 0 and complete and all(status == "ok" for _, status in entries)
              and log.rstrip().endswith("OK"))
    return {"original_test_entries": entries, "all_four_original_tests_executed": complete,
            "acceptance_passed": passed}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def case_evidence(kind, folder, log, returncode):
    if kind == "fixture":
        return fixture_evidence(log, returncode)
    if kind == "contact":
        value = read_json(folder / "contacts.json")
        return {"acceptance_passed": returncode == 0 and value.get("sources_unchanged") is True,
                "finite_ebrake_electrode_footprint_specified": False}
    if kind == "owned":
        value = read_json(folder / "ebrake-owned/report.json")
        return {"acceptance_passed": returncode == 0 and value.get("passed") is True,
                "cli_completed": value.get("cli_completed"), "can_sign_off": value.get("can_sign_off"),
                "convergence_status": value.get("convergence_status")}
    if kind == "rt0":
        value = read_json(folder / "marble-refined-rt0.json")
        return {"acceptance_passed": returncode == 0 and value.get("passed_dc_refinement_gate") is True,
                "relative_resistance_changes": value.get("relative_resistance_changes")}
    value = read_json(folder / "public-boards/readiness.json")
    return {"diagnostic_execution_completed": returncode == 0 and value.get("audit_execution_completed") is True,
            "full_board_pisi_ready": value.get("full_board_pisi_ready"),
            "cases": [{key: row.get(key) for key in ("name", "exit_code", "status", "error", "execution_error")}
                      for row in value.get("cases", [])]}


def acceptance_passed(cases, sources_before, sources_after, runtime_before, runtime_after):
    expected = {"native-contact-audit", "original-ebrake-fixture", "ebrake-owned-dc", "marble-refined-rt0"}
    required = [row for row in cases if row.get("required")]
    return (len(required) == len(expected) and {row["name"] for row in required} == expected
        and all(row.get("acceptance_passed") is True for row in required)
        and bool(sources_before) and sources_before == sources_after
        and runtime_before == runtime_after and runtime_before.get("native_available") is True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true", help="Retain plan/snapshot only; no simulation or acceptance claim")
    args = parser.parse_args()
    folder = args.output_dir.resolve()
    if (not folder.is_relative_to(ROOT / "build") or folder.exists()
            or any(part.startswith("qualification-") for part in folder.relative_to(ROOT).parts)):
        parser.error("Select a fresh build output folder outside qualification-owned directories")
    folder.mkdir(parents=True)
    before = source_snapshot()
    if any(before[spec[0]] != spec[1] for spec in BOARDS.values()):
        parser.error("Pinned board changed; preserve the original study")
    commands = plan(folder)
    (folder / "plan.json").write_text(json.dumps(commands, indent=2) + "\n", encoding="utf-8")
    report = {"contract": "spike/board-repair-acceptance-audit/v1", "production_qualified": False,
        "full_board_pisi_ready": False, "sources_before": before, "cases": [],
        "scope": "Unchanged original EBrake tests, opt-in DC and prior refined Marble RT0; public SI/PI admission remains diagnostic. No stage or release promotion."}
    if args.prepare_only:
        report.update(status="prepared_not_executed", repair_acceptance_passed=False)
    else:
        runtime_before = runtime_descriptor()
        report["runtime_before"] = runtime_before
        temp = folder / "temp"
        temp.mkdir()
        environment = dict(os.environ, SPIKE_FIXTURE_BOARD=str(ROOT / BOARDS["ebrake"][0]), TEMP=str(temp), TMP=str(temp))
        for entry in commands:
            if source_snapshot() != before:
                report["interrupted_reason"] = "Source changed; further simulation stopped to avoid mixed revisions"
                break
            started = perf_counter()
            row = dict(entry)
            try:
                result = subprocess.run(entry["command"], cwd=ROOT, env=environment,
                    capture_output=True, text=True, timeout=2400)
                log = result.stdout + result.stderr
                (folder / (entry["name"] + ".log")).write_text(log, encoding="utf-8")
                row.update(exit_code=result.returncode,
                    **case_evidence(entry["kind"], folder, log, result.returncode))
            except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                row.update(execution_error=str(error), acceptance_passed=False)
                partial = [getattr(error, key, None) or "" for key in ("stdout", "stderr")]
                log = "".join(value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value for value in partial)
                (folder / (entry["name"] + ".log")).write_text(log + "\n" + str(error), encoding="utf-8")
            row["elapsed_s"] = perf_counter()-started
            report["cases"].append(row)
            print(json.dumps({key: row.get(key) for key in ("name", "exit_code", "acceptance_passed", "execution_error")}), flush=True)
        report["runtime_after"] = runtime_descriptor()
        report["status"] = "executed"
    report["sources_after"] = source_snapshot()
    report["sources_unchanged"] = before == report["sources_after"]
    report["audit_execution_completed"] = (len(report["cases"]) == len(commands)
        and all(not row.get("execution_error") for row in report["cases"])
        and report["cases"][-1].get("diagnostic_execution_completed") is True)
    if not args.prepare_only:
        report["repair_acceptance_passed"] = report["audit_execution_completed"] and acceptance_passed(report["cases"], before,
            report["sources_after"], report["runtime_before"], report["runtime_after"])
    report["artifacts_sha256"] = {path.relative_to(folder).as_posix(): digest(path)
        for path in sorted(folder.rglob("*")) if path.is_file() and not path.is_relative_to(folder / "temp")}
    (folder / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "sources_unchanged", "repair_acceptance_passed", "full_board_pisi_ready")}))
    return 0 if args.prepare_only or report["repair_acceptance_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
