# SPDX-License-Identifier: Apache-2.0
"""Supplementary PI01-S02 execution; cannot complete or promote the full stage."""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.parity_pisi_gate import bound, digest, names
from scripts.parity_pi01_blockers_gate import validate_receipt as validate_previous
from python.spike_core.dc_annular_evidence import validate_annular_result, validate_annular_stack

MODULES = ("tests.python.test_dc_annular_land", "tests.python.test_dc_port_circuit",
           "tests.python.test_dc_annular_stack", "tests.python.test_dc_annular_source",
           "tests.python.test_dc_annular_evidence")
SOURCES = ("scripts/parity_annular_contact_gate.py", "python/spike_core/dc_annular_land.py",
    "python/spike_core/dc_annular_land_input.py", "python/spike_core/dc_annular_stack.py",
    "python/spike_core/dc_annular_stack_input.py", "python/spike_core/dc_port_circuit.py",
    "python/spike_core/dc_annular_source.py", "python/spike_core/kicad_source_evidence.py",
    "python/spike_core/dc_annular_evidence.py", "python/spike_core/kicad_importer.py",
    "python/core/board_parser.py", "python/spike_core/contracts.py",
    "python/core/kicad_model_sources.py", "python/core/filled_polygon_offset.py", "python/core/simple_polygon_union.py",
    "python/spike_core/board_outline_geometry.py", "python/spike_core/planar_polygon_topology.py",
    "python/spike_core/dc_axial_ownership.py", "python/spike_core/dc_land_transition.py",
    "python/spike_core/dc_land_transition_input.py", "python/spike_core/dc_land_transition_evidence.py",
    "scripts/check_architecture.py", "tests/python/test_dc_annular_land.py",
    "tests/python/test_dc_port_circuit.py", "tests/python/test_dc_annular_stack.py",
    "tests/python/test_dc_annular_source.py", "tests/python/test_dc_annular_evidence.py",
    "tests/fixtures/dc_annular_source.kicad_pcb", "docs/DC_ANNULAR_LAND.md",
    "docs/DC_ANNULAR_CIRCUIT.md", "docs/adr/0127-explicit-annular-field-circuit-ports.md",
    "examples/dc_annular_stack/run_stack.py", "examples/dc_annular_stack/three-land.request.json")
PREVIOUS = "docs/validation/parity/PI01-S02-land-transition-20261021.json"


def suite():
    return unittest.defaultTestLoader.loadTestsFromNames(MODULES)


def validate_report(report):
    from tests.python.test_dc_annular_land import spreading_request, finite_volume_spreading_resistance
    from tests.python.test_dc_annular_stack import explicit_annular_stack, series_resistance
    require = lambda condition, message: None if condition else fail(message)
    levels = report["annular_refinement"]
    require(len(levels) == 3, "Annular refinement missing")
    reference = finite_volume_spreading_resistance(128); coarse = finite_volume_spreading_resistance(64)
    require(abs(coarse/reference-1) < .002, "Independent annular reference not converged")
    errors = []
    for n, result in zip((4, 8, 16), levels):
        require(result["source_request"] == spreading_request(n), "Annular refinement support differs")
        validate_annular_result(result); errors.append(abs(result["joule_heat_w"]/reference-1))
    require(errors[0] > errors[1] > errors[2] and errors[-1] < .02, "Annular refinement failed")
    for key, spreading in (("series_stack", False), ("spreading_stack", True)):
        result = report[key]
        require(result["source_request"] == explicit_annular_stack(spreading=spreading), "Stack test input differs")
        validate_annular_stack(result)
    require(abs(report["series_stack"]["total_heat_w"]/series_resistance()-1) < 1e-9, "Physical series limit failed")
    wrapper = report["source_stack"]
    require(wrapper["contract"] == "spike/source-annular-stack-run/v1"
            and wrapper["source_files_revalidated"] is True and wrapper["production_qualified"] is False,
            "Native source wrapper scope differs")
    validate_annular_stack(wrapper["result"])
    from python.spike_core.dc_annular_source import verify_annular_pad_binding
    from tests.python.test_dc_annular_source import source_stack
    require(wrapper["result"]["source_request"] == source_stack(), "Source-backed acceptance input differs")
    for land in wrapper["result"]["source_request"]["lands"]:
        verify_annular_pad_binding(land["source_binding"])


def fail(message):
    raise ValueError(message)


def validate_receipt(receipt, root=ROOT):
    if (receipt.get("contract") != "spike/pi01-annular-contact-evidence/v1"
            or receipt.get("stage_id") != "PI01-S02" or receipt.get("status") != "passed"
            or receipt.get("stage_complete") is not False or receipt.get("production_qualified") is not False):
        fail("Annular partial evidence cannot complete the stage")
    before = receipt.get("sources_before", {})
    if set(before) != set(SOURCES) or before != receipt.get("sources_after"): fail("Annular source coverage/drift differs")
    for name, sha in before.items(): bound(root, name, sha)
    previous = bound(root, receipt.get("previous_evidence"), receipt.get("previous_sha256"))
    validate_previous(json.loads(previous.read_text(encoding="utf-8")), root)
    expected, execution = names(suite()), receipt.get("tests", {})
    if (not expected or any("_FailedTest" in n for n in expected) or execution.get("names") != expected
            or execution.get("run") != len(expected)
            or any(execution.get(key) != [] for key in ("failures", "errors", "skipped", "expected_failures", "unexpected_successes"))):
        fail("Annular execution incomplete or failed")
    log = bound(root, receipt.get("log"), receipt.get("log_sha256")).read_text(encoding="utf-8")
    if f"Ran {len(expected)} tests" not in log or not log.rstrip().endswith("OK"): fail("Annular log incomplete")
    report = json.loads(bound(root, receipt.get("report"), receipt.get("report_sha256")).read_text(encoding="utf-8"))
    validate_report(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "log", "report"): parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args(); paths = (args.output, args.log, args.report)
    if len({p.resolve() for p in paths}) != 3: parser.error("Outputs must differ")
    for path in paths:
        if path.exists() or not path.resolve().is_relative_to(ROOT): parser.error("Choose fresh repository outputs")
        path.parent.mkdir(parents=True, exist_ok=True)
    validate_previous(json.loads((ROOT/PREVIOUS).read_text(encoding="utf-8")))
    before = {n: digest(ROOT/n) for n in SOURCES}
    tests = suite(); expected = names(tests); stream = io.StringIO()
    run = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
    args.log.write_text(stream.getvalue(), encoding="utf-8")
    if not run.wasSuccessful() or run.skipped: fail("Annular suite failed; execution log retained")
    from tests.python.test_dc_annular_land import spreading_request
    from tests.python.test_dc_annular_stack import explicit_annular_stack
    from tests.python.test_dc_annular_source import source_stack
    from python.spike_core.dc_annular_land import solve_annular_land
    from python.spike_core.dc_annular_stack import solve_annular_stack
    from python.spike_core.dc_annular_source import solve_source_annular_stack
    report = {"annular_refinement": [solve_annular_land(spreading_request(n)) for n in (4, 8, 16)],
        "series_stack": solve_annular_stack(explicit_annular_stack()),
        "spreading_stack": solve_annular_stack(explicit_annular_stack(spreading=True)),
        "source_stack": solve_source_annular_stack(source_stack())}
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    after = {n: digest(ROOT/n) for n in SOURCES}
    receipt = {"contract": "spike/pi01-annular-contact-evidence/v1", "stage_id": "PI01-S02",
        "status": "passed" if before == after else "failed", "stage_complete": False, "production_qualified": False,
        "sources_before": before, "sources_after": after,
        "tests": {"names": expected, "run": run.testsRun, "failures": [], "errors": [], "skipped": [],
                  "expected_failures": [], "unexpected_successes": []},
        "previous_evidence": PREVIOUS, "previous_sha256": digest(ROOT/PREVIOUS),
        "log": args.log.resolve().relative_to(ROOT).as_posix(), "log_sha256": digest(args.log),
        "report": args.report.resolve().relative_to(ROOT).as_posix(), "report_sha256": digest(args.report)}
    args.output.write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    validate_receipt(receipt)
    print(json.dumps({"status": "passed", "tests": run.testsRun, "stage_complete": False}))


if __name__ == "__main__": main()
