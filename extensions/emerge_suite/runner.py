# SPDX-License-Identifier: Apache-2.0
"""Execute a generated planar PCB case with a separately installed EMerge."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from extensions.emerge_suite.capture import s_parameters, sphere_pattern, theta_cut


MM = 0.001
C0 = 299_792_458.0


def run_case(case: dict, em, *, radiation: bool) -> dict:
    if case.get("contract") != "spike/emerge-board-case/v1":
        raise ValueError("Unsupported EMerge board case.")
    import numpy as np

    model = em.Simulation("SPIKE_board")
    thickness = case["dielectric_thickness_mm"]
    pcb = em.geo.PCBNew(thickness, unit=MM, layers=2,
                        material=em.Material(case["epsilon_r"]),
                        trace_material=em.lib.PEC)
    for polygon in case["polygons"]:
        layer_index = -1 if polygon["layer"] == "F.Cu" else 0
        if str(em.__version__).startswith("3.0."):
            pcb.add_poly(polygon["xs_mm"], polygon["ys_mm"], layer=layer_index,
                         name=f"SPIKE_{polygon['id']}")
        else:
            pcb.add_poly(polygon["xs_mm"], polygon["ys_mm"], z=pcb.z(layer_index),
                         name=f"SPIKE_{polygon['id']}")
    traces = pcb.compile_paths(merge=False, fragment=case.get("fragment_copper", True))
    for via in case.get("shorting_vias", []):
        pcb.add_vias((via["x_mm"], via["y_mm"]), radius=via["radius_mm"])
    pcb.set_bounds(*case["bounds_mm"])
    pcb.generate_pcb(split_z=True, merge=True)
    shorts = pcb.generate_vias(merge=False) if case.get("shorting_vias") else []
    surroundings = []
    for item in case.get("surrounding_geometry", []):
        origin = [coordinate * MM for coordinate in item["origin_mm"]]
        size = [extent * MM for extent in item["size_mm"]]
        solid = em.geo.Box(*size, position=tuple(origin), name=item["name"])
        solid.set_material(em.Material(item["epsilon_r"]))
        surroundings.append(solid)
    # A bounded default for the absorbing region; the cap is recorded by the
    # adapter as an approximation and must be studied for convergence.
    margin_m = min(max(C0 / case["frequency_stop_hz"] / 4, 0.02), 0.1)
    air = em.geo.open_region(margin_m, margin_m, margin_m).background()
    ports = []
    for port in case["ports"]:
        width_m = port["width_mm"] * MM
        ports.append(em.geo.Plate(
            np.asarray([(port["x_mm"] - port["width_mm"] / 2) * MM,
                        port["y_mm"] * MM, -thickness * MM]),
            np.asarray([width_m, 0, 0]),
            np.asarray([0, 0, thickness * MM]),
        ))
    model.mw.set_frequency_range(case["frequency_start_hz"],
                                 case["frequency_stop_hz"], case["frequency_points"])
    model.commit_geometry()
    mesh_m = case["mesh_resolution_mm"] * MM
    model.mesher.set_boundary_size(traces, mesh_m)
    for short in shorts:
        model.mesher.set_boundary_size(short, mesh_m)
    for solid in surroundings:
        model.mesher.set_boundary_size(solid, mesh_m)
    for plate, port in zip(ports, case["ports"]):
        model.mesher.set_face_size(plate, min(mesh_m, port["width_mm"] * MM / 3))
    model.generate_mesh()
    for index, (plate, port) in enumerate(zip(ports, case["ports"]), 1):
        model.mw.bc.LumpedPort(plate, index, width=port["width_mm"] * MM,
                               height=thickness * MM, direction=em.ZAX,
                               Z0=port["reference_impedance_ohm"])
    boundary = air.boundary()
    model.mw.bc.AbsorbingBoundary(boundary)
    data = model.mw.run_sweep()
    port_names = [f"P{index}" for index in range(1, len(ports) + 1)]
    result = {"engine_version": str(em.__version__),
              "s_parameters": s_parameters(data, port_names, 50.0),
              "air_margin_m": margin_m}
    if radiation:
        frequencies = result["s_parameters"]["frequencies_hz"]
        angles = [float(value) for value in range(0, 181, 5)]
        cuts = [theta_cut(data.field.find(freq=frequency), boundary,
                          frequency, angles, phi_deg=0.0)
                for frequency in frequencies]
        theta = [float(value) for value in range(0, 181, 15)]
        phi = [float(value) for value in range(0, 361, 15)]
        patterns = [sphere_pattern(data.field.find(freq=frequency), boundary,
                                   frequency, theta, phi)
                    for frequency in frequencies]
        result["radiation"] = {"frequencies_hz": frequencies, "cuts": cuts,
                               "patterns_3d": patterns}
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--radiation", action="store_true")
    args = parser.parse_args()
    case = json.loads(Path(args.case).read_text(encoding="utf-8"),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    import emerge as em

    result = run_case(case, em, radiation=args.radiation)
    output = Path(args.result)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(json.dumps(result, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, output)


if __name__ == "__main__":
    main()
