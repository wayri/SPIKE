# SPDX-License-Identifier: Apache-2.0
"""Source-bound experimental PI01-S02 board-volume increment evidence."""
from __future__ import annotations
import argparse
from copy import deepcopy
import io
import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.parity_pisi_gate import bound, digest, names
from python.spike_core.solvers.power_integrity.dc.dc_board_study import validate_source_board_run
from python.spike_core.solvers.power_integrity.dc.dc_tetra_rt0_evidence import validate_tetra_dc

MODULES = ("tests.python.test_dc_tetra_rt0", "tests.python.test_dc_tetra_evidence",
    "tests.python.test_dc_board_volume", "tests.python.test_dc_board_filled",
    "tests.python.test_kicad_board_source_inventory", "tests.python.test_dc_board_source",
    "tests.python.test_dc_board_study", "tests.python.test_dc_board_review")
SOURCES = ("scripts/parity_board_volume_gate.py", "tests/python/test_board_volume_gate.py",
    "python/spike_core/solvers/power_integrity/dc/dc_tetra_rt0.py", "python/spike_core/solvers/power_integrity/dc/dc_tetra_rt0_input.py",
    "python/spike_core/solvers/power_integrity/dc/dc_tetra_rt0_evidence.py", "python/spike_core/solvers/power_integrity/dc/dc_tetra_density.py",
    "python/spike_core/solvers/power_integrity/dc/dc_board_volume.py", "python/spike_core/solvers/power_integrity/dc/dc_board_filled.py",
    "python/spike_core/solvers/power_integrity/dc/dc_board_source.py", "python/spike_core/solvers/power_integrity/dc/dc_board_study.py",
    "python/spike_core/solvers/power_integrity/dc/dc_copper_domain.py", "python/spike_core/solvers/power_integrity/dc/dc_triangle_partition.py",
    "python/spike_core/solvers/thermal_fluid/heat/assembly_tetra_thermal_validation.py", "python/spike_core/solvers/geometry_meshing/preparation/tetra_aabb_candidates.py",
    "python/spike_core/solvers/power_integrity/dc/dc_land_transition.py", "python/spike_core/solvers/power_integrity/dc/dc_land_transition_evidence.py",
    "python/spike_core/solvers/power_integrity/dc/dc_rt0_density.py", "python/spike_core/solvers/power_integrity/dc/hybrid_owned_copper.py",
    "python/spike_core/layers.py", "python/spike_core/solvers/geometry_meshing/preparation/boundary_spatial_index.py",
    "python/spike_core/solvers/geometry_meshing/preparation/planar_polygon_topology.py", "python/spike_core/board_outline_geometry.py",
    "python/spike_core/solvers/power_integrity/dc/filled_copper_path.py", "python/spike_core/solvers/power_integrity/dc/source_filled_boundary.py",
    "python/spike_core/kicad_source_evidence.py", "python/spike_core/kicad_importer.py",
    "python/spike_core/solvers/geometry_meshing/preparation/hybrid_mesh.py", "python/spike_core/solvers/power_integrity/pdn/quasistatic_copper_area.py",
    "python/core/board_parser.py", "python/core/kicad_model_sources.py",
    "python/core/filled_polygon_offset.py", "python/core/simple_polygon_union.py",
    "python/spike_core/contracts.py", "scripts/benchmark_board_volume_dc.py",
    "examples/dc_board_volume/run_volume.py", "examples/dc_board_volume/holed-board.request.json",
    "tests/python/test_dc_tetra_rt0.py", "tests/python/test_dc_tetra_evidence.py",
    "tests/python/test_dc_board_volume.py", "tests/python/test_dc_board_filled.py",
    "tests/python/test_kicad_board_source_inventory.py", "tests/python/test_dc_board_source.py",
    "tests/python/test_dc_board_study.py", "tests/python/test_dc_board_review.py",
    "tests/fixtures/dc_board_volume_source.kicad_pcb",
    "tests/fixtures/dc_annular_source.kicad_pcb", "docs/DC_TETRA_RT0.md",
    "docs/DC_TETRA_RT0_ORACLES.md", "docs/adr/0134-conservative-board-volume-dc-reference.md")


def fail(message):
    raise ValueError(message)


def require(condition, message):
    if not condition:
        fail(message)


def canonical(value):
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))


def suite():
    return unittest.defaultTestLoader.loadTestsFromNames(MODULES)


def source_config():
    from tests.python.test_dc_board_source import source_model, FIXTURE
    prepared = source_model()
    return {"contract": "spike/source-board-volume-study/v1", "source_path": str(FIXTURE),
        "source_sha256": digest(FIXTURE), "net_names": ["VDD"],
        "electrodes": prepared["source_evidence"]["electrodes"], "plating_thickness_mm": .025,
        "conductivity_s_m": 5.8e7, "target_mm": 1., "max_cells": 5000}


def annular_config():
    import hashlib
    from tests.python.test_dc_annular_source import FIXTURE, PAD_UUID
    return {"source_path": str(FIXTURE), "source_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "net_names": ["STACK"],
        "electrodes": [{"id": "source", "pad_id": PAD_UUID, "layer": "B.Cu", "side": "bottom", "current_a": 1.},
                       {"id": "load", "pad_id": PAD_UUID, "layer": "F.Cu", "side": "top", "current_a": -1.}],
        "plating_thickness_mm": .025, "conductivity_s_m": 5.8e7, "target_mm": 2., "max_cells": 5000}


def build_report():
    from python.spike_core.solvers.power_integrity.dc.dc_board_source import prepare_source_board
    from python.spike_core.solvers.power_integrity.dc.dc_board_volume import compile_board_volume
    from python.spike_core.solvers.power_integrity.dc.dc_board_study import solve_source_board
    from python.spike_core.solvers.power_integrity.dc.dc_tetra_rt0 import solve_tetra_dc
    from tests.python.test_dc_board_volume import compile_fixture
    from tests.python.test_dc_tetra_rt0 import continuum_request
    compiled = compile_fixture(target_mm=.8)
    annular = annular_config()
    prepared = prepare_source_board(annular["source_path"], annular["source_sha256"],
        net_names=annular["net_names"], electrodes=annular["electrodes"],
        plating_thickness_mm=annular["plating_thickness_mm"], conductivity_s_m=annular["conductivity_s_m"])
    annular_compiled = compile_board_volume(prepared["groups"], prepared["barrels"], prepared["contacts"],
        expected_axial_source_ids=prepared["expected_axial_source_ids"],
        target_mm=annular["target_mm"], max_cells=annular["max_cells"])
    return {"harmonic": [solve_tetra_dc(continuum_request(n)) for n in (1, 2, 4)],
        "generic_board_volume": {"compiled": compiled, "result": solve_tetra_dc(compiled["request"])},
        "native_source_wrapper": solve_source_board(source_config()),
        "native_annular_pipeline": {"config": annular, "source_evidence": prepared["source_evidence"],
            "electrode_evidence": prepared["electrode_evidence"], "compiled": annular_compiled,
            "result": solve_tetra_dc(annular_compiled["request"])}}


def _harmonic_error(raw, result):
    from tests.python.test_dc_tetra_rt0 import quadrature
    error_squared = 0.0
    points = np.asarray(raw["mesh"]["vertices"], dtype=float)
    for cell in result["cells"]:
        samples = quadrature() @ points[cell["vertices"]]
        exact = np.column_stack((-samples[:, 1], -samples[:, 0], np.zeros(4)))
        actual = quadrature() @ np.asarray(cell["vertex_density_a_m2"], dtype=float)
        error_squared += cell["volume_m3"] * float(np.mean(np.sum((actual-exact)**2, axis=1)))
    return math.sqrt(error_squared), abs(result["joule_heat_w"] - 2/3)


def validate_report(report):
    from tests.python.test_dc_board_volume import compile_fixture
    from tests.python.test_dc_tetra_rt0 import continuum_request, radial_cube_quantile
    harmonic = report.get("harmonic")
    require(isinstance(harmonic, list) and len(harmonic) == 3, "Harmonic witness set differs")
    field_errors, heat_errors = [], []
    for n, result in zip((1, 2, 4), harmonic):
        raw = continuum_request(n)
        require(result.get("source_request") == raw, "Harmonic request provenance differs")
        validate_tetra_dc(result)
        field, heat = _harmonic_error(raw, result)
        field_errors.append(field); heat_errors.append(heat)
    require(all(b < .65*a for a, b in zip(field_errors, field_errors[1:]))
            and field_errors[-1] < .12, "Harmonic field refinement differs")
    require(all(b < .4*a for a, b in zip(heat_errors, heat_errors[1:]))
            and heat_errors[-1] < .02, "Harmonic energy refinement differs")
    for name, probability in (("p95", .95), ("p99", .99)):
        interval = harmonic[-1]["current_density_observable"][name]
        expected = radial_cube_quantile(probability)
        require(abs(interval["lower_a_m2"]/expected-1) < .1
                and abs(interval["upper_a_m2"]/expected-1) < .1,
                "Harmonic physical-volume quantile differs")

    generic = report.get("generic_board_volume", {})
    expected = compile_fixture(target_mm=.8)
    require(canonical(generic.get("compiled")) == canonical(expected),
            "Generic board-volume geometry/coverage differs")
    result = generic.get("result", {})
    require(result.get("source_request") == expected["request"], "Generic board result detached")
    validate_tetra_dc(result)
    coverage = generic["compiled"]["coverage"]
    require(coverage.get("complete_selected_geometry") is True
            and coverage.get("no_intentional_geometry_omission") is True
            and len(coverage.get("volumes", [])) == 4
            and all(row["footprint_overlay_audit"]["accepted"] for row in coverage["volumes"]),
            "Generic retained volume/coverage evidence differs")

    wrapper = report.get("native_source_wrapper", {})
    require(wrapper.get("source_request") == source_config(), "Native source request differs")
    validate_source_board_run(wrapper)
    require(wrapper.get("source_revalidated_after_solve") is True
            and wrapper.get("production_qualified") is False
            and wrapper.get("full_board_pisi_ready") is False
            and wrapper["source_evidence"]["source_sha256"] == wrapper["source_request"]["source_sha256"],
            "Native source identity/scope differs")
    require(wrapper["run"]["coverage"]["complete_selected_geometry"] is True
            and wrapper["run"]["result"]["current_density_observable"]["complete_board_physical_volume"] is False,
            "Native selected-volume scope differs")

    from python.spike_core.solvers.power_integrity.dc.dc_board_source import prepare_source_board
    from python.spike_core.solvers.power_integrity.dc.dc_board_volume import compile_board_volume
    annular = report.get("native_annular_pipeline", {})
    config = annular.get("config", {})
    require(config == annular_config(), "Native annular configuration differs")
    prepared = prepare_source_board(config["source_path"], config["source_sha256"],
        net_names=config["net_names"], electrodes=config["electrodes"],
        plating_thickness_mm=config["plating_thickness_mm"], conductivity_s_m=config["conductivity_s_m"])
    expected = compile_board_volume(prepared["groups"], prepared["barrels"], prepared["contacts"],
        expected_axial_source_ids=prepared["expected_axial_source_ids"],
        target_mm=config["target_mm"], max_cells=config["max_cells"])
    require(canonical(annular.get("source_evidence")) == canonical(prepared["source_evidence"])
            and canonical(annular.get("electrode_evidence")) == canonical(prepared["electrode_evidence"])
            and canonical(annular.get("compiled")) == canonical(expected),
            "Native annular source/geometry evidence differs")
    result = annular.get("result", {})
    require(result.get("source_request") == expected["request"], "Native annular field detached")
    validate_tetra_dc(result)
    require(expected["request"]["mesh"]["counts"]["cells"] <= config["max_cells"]
            and len(expected["coverage"]["volumes"]) == 3
            and len(expected["coverage"]["contacts"]) == 2,
            "Native annular complete-volume topology differs")


def validate_receipt(receipt, root=ROOT):
    require(receipt.get("contract") == "spike/pi01-board-volume-evidence/v1"
            and receipt.get("stage_id") == "PI01-S02" and receipt.get("status") == "passed"
            and receipt.get("stage_complete") is False and receipt.get("production_qualified") is False,
            "Board-volume increment cannot complete or qualify the stage")
    before = receipt.get("sources_before", {})
    require(set(before) == set(SOURCES) and before == receipt.get("sources_after"),
            "Board-volume source coverage/drift differs")
    for name, sha in before.items():
        bound(root, name, sha)
    expected, execution = names(suite()), receipt.get("tests", {})
    require(len(expected) == 47 and execution.get("names") == expected
            and execution.get("run") == len(expected)
            and not any("_FailedTest" in name for name in expected)
            and all(execution.get(key) == [] for key in
                    ("failures", "errors", "skipped", "expected_failures", "unexpected_successes")),
            "Board-volume focused execution incomplete or failed")
    log = bound(root, receipt.get("log"), receipt.get("log_sha256")).read_text(encoding="utf-8")
    require(f"Ran {len(expected)} tests" in log and log.rstrip().endswith("OK"),
            "Board-volume execution log incomplete")
    report = json.loads(bound(root, receipt.get("report"), receipt.get("report_sha256")).read_text(encoding="utf-8"))
    validate_report(report)
    require(isinstance(receipt.get("board_audits"), list), "Board audit bindings must be a list")
    for audit in receipt["board_audits"]:
        require(set(audit) == {"path", "sha256"}, "Board audit binding is malformed")
        json.loads(bound(root, audit["path"], audit["sha256"]).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "log", "report"):
        parser.add_argument("--"+name, required=True, type=Path)
    parser.add_argument("--board-audit", action="append", default=[], type=Path,
                        help="Optional completed real-board blocked/admitted audit JSON to bind")
    args = parser.parse_args(); paths = (args.output, args.log, args.report)
    if len({path.resolve() for path in paths}) != 3:
        parser.error("Outputs must differ")
    for path in paths:
        if path.exists() or not path.resolve().is_relative_to(ROOT):
            parser.error("Choose fresh repository outputs")
        path.parent.mkdir(parents=True, exist_ok=True)
    before = {name: digest(ROOT/name) for name in SOURCES}
    audits = []
    for path in args.board_audit:
        resolved = path.resolve()
        if not resolved.is_relative_to(ROOT) or not resolved.is_file():
            parser.error("Board audits must be existing repository JSON files")
        json.loads(resolved.read_text(encoding="utf-8"))
        audits.append({"path": resolved.relative_to(ROOT).as_posix(), "sha256": digest(resolved)})
    tests = suite(); expected = names(tests); stream = io.StringIO()
    run = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
    args.log.write_text(stream.getvalue(), encoding="utf-8")
    if not run.wasSuccessful() or run.skipped or run.testsRun != 47:
        fail("Board-volume focused suite failed; execution log retained")
    report = build_report()
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    validate_report(report)
    after = {name: digest(ROOT/name) for name in SOURCES}
    receipt = {"contract": "spike/pi01-board-volume-evidence/v1", "stage_id": "PI01-S02",
        "status": "passed" if before == after else "failed", "stage_complete": False,
        "production_qualified": False, "sources_before": before, "sources_after": after,
        "tests": {"names": expected, "run": run.testsRun, "failures": [], "errors": [], "skipped": [],
                  "expected_failures": [], "unexpected_successes": []},
        "board_audits": audits,
        "log": args.log.resolve().relative_to(ROOT).as_posix(), "log_sha256": digest(args.log),
        "report": args.report.resolve().relative_to(ROOT).as_posix(), "report_sha256": digest(args.report)}
    args.output.write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    validate_receipt(receipt)
    print(json.dumps({"status": "passed", "tests": run.testsRun, "stage_complete": False}))


if __name__ == "__main__":
    main()
