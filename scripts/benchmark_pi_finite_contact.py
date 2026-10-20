# SPDX-License-Identifier: Apache-2.0
"""Offline analytical finite-contact DC ladder; no board qualification.

Derivation, primary references and frozen tolerances:
docs/PI_FINITE_CONTACT_BENCHMARK.md. Uses existing experimental RT0 kernels.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TARGETS = (0.5, 0.25, 0.125)
LIMITS = {"resistance_relative": 0.002, "density_relative": 0.02,
          "volume_absolute_mm3": 1e-10, "kcl_absolute_a": 1e-8,
          "residual_relative": 1e-7, "energy_relative": 1e-7}
CASES = (
    {"id": "base", "angle_rad": 0., "geometry_grid_mm": 0., "conductivity_s_m": 5.8e7, "inactive_area_mm2": 0.},
    {"id": "rotated", "angle_rad": 0.61, "geometry_grid_mm": 1e-12, "conductivity_s_m": 5.8e7, "inactive_area_mm2": 0.},
    {"id": "double_conductivity", "angle_rad": 0., "geometry_grid_mm": 0., "conductivity_s_m": 1.16e8, "inactive_area_mm2": 0.},
    {"id": "inactive_island", "angle_rad": 0., "geometry_grid_mm": 0., "conductivity_s_m": 5.8e7, "inactive_area_mm2": 0.5},
)
FIXED = {"length_mm": 2., "width_mm": 1., "contact_length_mm": 0.5,
         "thickness_mm": 0.035, "current_a": 1., "contact_ids": ["source", "load"],
         "contact_areas_mm2": [0.5, 0.5],
         "contact_model": "uniform finite-area current injection; area-average potential"}


def reference(case):
    """Closed form from conservation and work; independent of RT0 assembly."""
    k = case["conductivity_s_m"] * FIXED["thickness_mm"] * 1e-3
    resistance = (FIXED["length_mm"] - 4*FIXED["contact_length_mm"]/3)/(k*FIXED["width_mm"])
    return {"resistance_ohm": resistance, "dissipation_w": resistance,
            "p95_a_mm2": 1/FIXED["thickness_mm"], "p99_a_mm2": 1/FIXED["thickness_mm"],
            "volume_mm3": (2 + case["inactive_area_mm2"])*FIXED["thickness_mm"],
            "inactive_volume_mm3": case["inactive_area_mm2"]*FIXED["thickness_mm"]}


def solve_level(case, target):
    from shapely.affinity import rotate
    from shapely.geometry import box
    from python.spike_core.dc_triangle_partition import partition_polygon_groups
    from python.spike_core.peec_conforming_dc import solve_hybridized_conforming_dc
    shape = box(0, 0, 2, 1)
    if case["inactive_area_mm2"]:
        shape = shape.union(box(3, 0, 3.5, 1))
    transform = lambda shape: rotate(shape, case["angle_rad"], origin=(0, 0), use_radians=True)
    groups = {("F.Cu", "N"): {"geometry": transform(shape), "thickness_mm": FIXED["thickness_mm"],
              "conductivity_s_m": case["conductivity_s_m"], "z_mm": 0.}}
    contacts = [{"id": name, "layer": "F.Cu", "net": "N", "geometry": transform(geometry)}
                for name, geometry in zip(FIXED["contact_ids"], (box(0, 0, .5, 1), box(1.5, 0, 2, 1)))]
    mesh = partition_polygon_groups(groups, contacts, target_mm=target, max_triangles=20000,
        geometry_grid_mm=case["geometry_grid_mm"])
    support = mesh.branch_admission["conforming_partition"]["terminal_contacts"]
    nodes = {contact["id"]: contact["node"] for contact in support}
    result = solve_hybridized_conforming_dc(mesh, nodes["source"], nodes["load"],
        max_unknowns=50000, max_triangles=20000, include_density=True)
    return {"target_mm": target, "contacts": deepcopy(support), "result": result,
            "geometry_audit": deepcopy(mesh.branch_admission["conforming_partition"]["groups"])}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Finite-contact evidence requires finite real numbers")
    return value


def _integer(value, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError("Finite-contact identity/count requires an integer")
    return value


def assess(case, levels):
    """Recompute every decision from raw levels, never trust a saved pass flag."""
    if not isinstance(levels, list) or len(levels) != len(TARGETS):
        raise ValueError("Finite-contact evidence needs all three ordered levels")
    exact, errors, previous_count = reference(case), [], 0
    for target, level in zip(TARGETS, levels):
        if level["target_mm"] != target:
            raise ValueError("Finite-contact level identity/order differs")
        audits = level["geometry_audit"]
        if len(audits) != 1 or (audits[0]["layer"], audits[0]["net"]) != ("F.Cu", "N"):
            raise ValueError("Finite-contact geometry audit identity differs")
        geometry = audits[0]
        source_area = 2+case["inactive_area_mm2"]
        if abs(_number(geometry["source_area_mm2"])-source_area) > 1e-12:
            raise ValueError("Finite-contact source area differs")
        for key in ("omitted_area_mm2", "outside_area_mm2", "overlap_area_mm2"):
            if not 0 <= _number(geometry[key]) <= max(1e-11, source_area*1e-11):
                raise ValueError("Finite-contact geometry conservation failed")
        if case["geometry_grid_mm"]:
            precision = geometry["precision_geometry"]
            grid = case["geometry_grid_mm"]
            if (precision["grid_mm"] != grid or precision["formal_roundoff_certificate"] is not False
                    or precision["method"] != "explicit_fixed_grid_noded_original_linework"
                    or [p["id"] for p in precision["contacts"]] != FIXED["contact_ids"]):
                raise ValueError("Finite-contact precision model identity differs")
            for support, area, perimeter in zip([precision["copper"], *precision["contacts"]],
                                                (2., .5, .5), (6., 3., 3.)):
                expected_area_budget = 8*grid*perimeter + math.pi*(4*grid)**2
                if (support["boundary_budget_mm"] != 4*grid
                        or not 0 <= _number(support["boundary_displacement_mm"]) <= 4*grid
                        or not 0 <= _number(support["symmetric_difference_mm2"]) <= _number(support["area_budget_mm2"])
                        or not 0 < _number(support["area_budget_mm2"]) <= expected_area_budget*(1+1e-12)
                        or abs(_number(support["source_area_mm2"])-area) > 1e-12
                        or abs(_number(support["admitted_area_mm2"])-area) > expected_area_budget
                        or support["components"] != 1 or support["hole_counts"] != [0]):
                    raise ValueError("Finite-contact precision uncertainty/topology failed")
        contacts = level["contacts"]
        if len(contacts) != 2 or [c["id"] for c in contacts] != FIXED["contact_ids"]:
            raise ValueError("Finite-contact identities differ")
        for contact in contacts:
            _integer(contact["node"])
            if (contact["layer"] != "F.Cu" or contact["net"] != "N"
                    or abs(_number(contact["area_mm2"])-.5) > 1e-12):
                raise ValueError("Finite-contact support differs")
        if contacts[0]["node"] == contacts[1]["node"]:
            raise ValueError("Finite-contact node identities collapse")
        r = level["result"]
        field = r["current_density_observable"]
        count = _integer(r["triangle_count"], 1)
        if count <= previous_count:
            raise ValueError("Finite-contact refinement triangle counts must increase")
        previous_count = count
        if (r["model_status"] != "experimental" or r["production_qualified"] is not False
                or r["contact_model"] != FIXED["contact_model"]
                or r["method"] != "conforming_triangle_RT0_hybridized_DC"
                or field["method"] != "RT0_signed_flux_vector_unique_planar_volume"
                or field["complete_physical_volume"] is not False
                or field["complete_planar_polygon_partition"] is not True
                or field["axial_barrel_count"] != 0 or field["axial_support_status"] != "not_present"):
            raise ValueError("Finite-contact solver scope or physical ownership differs")
        for key, limit in (("maximum_cell_kcl_error_a", "kcl_absolute_a"),
                           ("maximum_face_kcl_error_a", "kcl_absolute_a"),
                           ("relative_residual", "residual_relative"),
                           ("relative_energy_error", "energy_relative")):
            if not 0 <= _number(r[key]) < LIMITS[limit]:
                raise ValueError("Finite-contact conservation/work check failed")
        for actual, expected in ((field["physical_planar_volume_mm3"], exact["volume_mm3"]),
                                 (field["undriven_planar_volume_mm3"], exact["inactive_volume_mm3"])):
            if abs(_number(actual)-expected) >= LIMITS["volume_absolute_mm3"]:
                raise ValueError("Finite-contact physical volume differs")
        error = {"target_mm": target,
                 "resistance_relative": abs(_number(r["resistance_ohm"])/exact["resistance_ohm"]-1),
                 "heat_relative": abs(_number(field["planar_dissipation_w"])/exact["dissipation_w"]-1)}
        if abs(_number(r["dissipation_w_at_one_ampere"])-field["planar_dissipation_w"]) > 1e-7*exact["dissipation_w"]:
            raise ValueError("Finite-contact planar heat and terminal work differ")
        if any(_number(value) <= 0 for value in (r["resistance_ohm"],
                r["dissipation_w_at_one_ampere"], field["planar_dissipation_w"])):
            raise ValueError("Finite-contact resistance and heat must be positive")
        # At I=1 A the conjugate terminal work is R watts. Do not trust only
        # the saved solver diagnostic: bind this invariant to raw quantities.
        if abs(r["dissipation_w_at_one_ampere"]-r["resistance_ohm"])/r["resistance_ohm"] >= LIMITS["energy_relative"]:
            raise ValueError("Finite-contact raw terminal-work balance failed")
        for name, quantile in (("p95", .95), ("p99", .99)):
            p = field[name]
            if (_integer(p["original_triangle_count"], 1) < count
                    or _integer(p["quadrature_subcell_count"], 1) < p["original_triangle_count"]):
                raise ValueError("Finite-contact percentile support count differs")
            lo, hi = _number(p["lower_a_mm2"]), _number(p["upper_a_mm2"])
            if (p["converged"] is not True or p["quantile"] != quantile or not 0 <= lo <= hi
                    or abs(_number(p["physical_volume_mm3"])-exact["volume_mm3"]) >= LIMITS["volume_absolute_mm3"]
                    or abs(_number(p["enclosure_width_a_mm2"])-(hi-lo)) > 1e-12
                    or hi-lo > 1e-10 + 1e-6*hi):
                raise ValueError("Finite-contact percentile enclosure is invalid")
            error[name+"_relative"] = max(abs(lo/exact[name+"_a_mm2"]-1), abs(hi/exact[name+"_a_mm2"]-1))
        errors.append(error)
    passed = (errors[-1]["resistance_relative"] < LIMITS["resistance_relative"]
              and errors[-1]["resistance_relative"] < errors[0]["resistance_relative"]
              and errors[-1]["heat_relative"] < LIMITS["resistance_relative"]
              and all(errors[-1][name+"_relative"] < LIMITS["density_relative"] for name in ("p95", "p99")))
    return {"status": "passed" if passed else "failed", "errors": errors}


def run_benchmark():
    cases = []
    for case in CASES:
        levels = [solve_level(case, target) for target in TARGETS]
        cases.append({"fixture": deepcopy(case), "reference": reference(case), "levels": levels,
                      "assessment": assess(case, levels)})
    return {"contract": "spike/pi-finite-contact-benchmark/v1", "production_qualified": False,
            "fixed": deepcopy(FIXED), "limits": deepcopy(LIMITS), "cases": cases,
            "status": "passed" if all(c["assessment"]["status"] == "passed" for c in cases) else "failed"}


def validate_report(report):
    if (report.get("contract") != "spike/pi-finite-contact-benchmark/v1"
            or report.get("production_qualified") is not False or report.get("fixed") != FIXED
            or report.get("limits") != LIMITS or len(report.get("cases", [])) != len(CASES)):
        raise ValueError("Finite-contact benchmark identity/tolerances differ")
    for expected, case in zip(CASES, report["cases"]):
        if case["fixture"] != expected or case["reference"] != reference(expected):
            raise ValueError("Finite-contact analytical fixture/reference differs")
        assessment = assess(expected, case["levels"])
        if case["assessment"] != assessment or assessment["status"] != "passed":
            raise ValueError("Finite-contact benchmark failed or assessment differs")
    if report.get("status") != "passed":
        raise ValueError("Finite-contact benchmark failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path = args.output.resolve()
    if not path.is_relative_to(ROOT) or path.exists():
        parser.error("Choose a fresh repository output path")
    path.parent.mkdir(parents=True, exist_ok=True)
    report = run_benchmark()
    path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    validate_report(report)
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]), "levels_per_case": len(TARGETS)}))


if __name__ == "__main__":
    main()
