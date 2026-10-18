# SPDX-License-Identifier: Apache-2.0
"""Original analytic black-box fixtures; run with the installed FreeCAD Python."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time

import FreeCAD as App
import Part

REPO = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("scale_worker", REPO / "python/spike_core/freecad_scale_step.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
RUN = REPO / 'build/step-scale-replay' / ("native-" + time.strftime("%Y%m%d-%H%M%S"))
RUN.mkdir(parents=True)
rows = []


def run(name, shape, scale, expected_volume=None, expected_bounds=None, reject=None, mutate=None):
    root = RUN / name
    root.mkdir()
    shape.exportStep(str(root / "source.step"))
    request = {"scale_xyz": scale, "source_sha256": hashlib.sha256((root / "source.step").read_bytes()).hexdigest()}
    if mutate:
        mutate(request, root)
    (root / "request.json").write_text(json.dumps(request), encoding="utf-8")
    try:
        facts = worker.scale_step(str(root))
    except Exception as exc:
        message = str(exc)
        assert reject and reject in message, (name, message, reject)
        assert not (root / "facts.json").exists()
        rows.append({"name": name, "status": "expected_rejection", "message": message})
        return
    assert reject is None, name
    assert facts == json.loads((root / "facts.json").read_text())
    assert facts["output_sha256"] == hashlib.sha256((root / "scaled.step").read_bytes()).hexdigest()
    assert facts["source_sha256"] == request["source_sha256"]
    assert facts["scale_xyz"] == scale
    for key in ("scaled", "roundtrip"):
        item = facts[key]
        assert item["solid_count"] == 1 and item["valid"] and item["closed"]
        assert math.isclose(item["volume_mm3"], expected_volume, rel_tol=1e-8, abs_tol=0), (name, key, item)
        assert all(math.isclose(a, b, rel_tol=1e-9, abs_tol=2e-6)
                   for a, b in zip(item["bounds_mm"], expected_bounds)), (name, key, item)
    if facts["source"]["vertices_status"] == "complete":
        expected_vertices = [[s * v for s, v in zip(scale, p)] for p in facts["source"]["vertices_mm"]]
        for key in ("scaled", "roundtrip"):
            actual = list(facts[key]["vertices_mm"])
            for expected in expected_vertices:
                index = next(i for i, p in enumerate(actual) if all(abs(a-b) <= 1e-8 for a,b in zip(p,expected)))
                actual.pop(index)
            assert not actual
    else:
        assert all("vertices_mm" not in facts[key] for key in ("source", "scaled", "roundtrip"))
    rows.append({"name": name, "status": "passed", "volume_mm3": facts["roundtrip"]["volume_mm3"],
                 "bounds_mm": facts["roundtrip"]["bounds_mm"], "vertices_status": facts["roundtrip"]["vertices_status"]})


box = Part.makeBox(2, 3, 4)
run("box_2x3x4", box, [2, 1, .5], 24, [0, 0, 0, 4, 3, 2])
translated = Part.makeBox(2, 3, 4, App.Vector(-3, 5, 7))
run("translated_box", translated, [2, 1, .5], 24, [-6, 5, 3.5, -2, 8, 5.5])
triangle = Part.makePolygon([App.Vector(0,0,0), App.Vector(2,0,0), App.Vector(0,3,0), App.Vector(0,0,0)])
wedge = Part.Face(triangle).extrude(App.Vector(0,0,4))
run("triangular_prism", wedge, [3, .5, 2], 36, [0, 0, 0, 6, 1.5, 8])
run("identity_box", box, [1, 1, 1], 24, [0, 0, 0, 2, 3, 4])
run("uniform_box", box, [.5, .5, .5], 3, [0, 0, 0, 1, 1.5, 2])
ring = [App.Vector(2*math.cos(2*math.pi*i/130), 2*math.sin(2*math.pi*i/130), 0) for i in range(130)]
polygon = Part.Face(Part.makePolygon(ring + ring[:1])).extrude(App.Vector(0,0,3))
v = 130 / 2 * 4 * math.sin(2*math.pi/130) * 3
run("bounded_vertex_omission", polygon, [2,1,.5], v,
    [-4, min(p.y for p in ring), 0, 4, max(p.y for p in ring), 1.5])
run("cylinder_fail_closed", Part.makeCylinder(2,4), [2,1,.5], reject="determinant-scaled volume")
run("sheet_rejected", Part.makePlane(2,3), [2,1,.5], reject="exactly one valid closed solid")
run("multiple_solids_rejected", Part.makeCompound([box, translated]), [2,1,.5], reject="exactly one valid closed solid")
run("mixed_sheet_rejected", Part.makeCompound([box, Part.makePlane(2,3,App.Vector(5,5,5))]), [2,1,.5], reject="mixed solid")
for name, scale in (("zero",[0,1,1]), ("mirror",[-1,1,1]), ("boolean",[True,1,1]),
                    ("too_small",[.0001,1,1]), ("too_large",[1001,1,1]), ("nan",[float("nan"),1,1])):
    run(name, box, scale, reject="finite numbers")
run("digest_rejected",box,[1,1,1],reject="does not match",mutate=lambda r,p:r.update(source_sha256="0"*64))
run("path_field_rejected",box,[1,1,1],reject="request fields",mutate=lambda r,p:r.update(source_path="elsewhere.step"))
run("budget_rejected",box,[1,1,1],reject="byte budget",mutate=lambda r,p:(p/"source.step").write_bytes(b" "*(worker.MAX_STEP_BYTES+1)))
report = {"freecad_version": App.Version(), "worker_sha256": hashlib.sha256((REPO/"python/spike_core/freecad_scale_step.py").read_bytes()).hexdigest(),
          "fixture_provenance": "Original SPIKE analytic primitives; no vendor fixtures or implementation read",
          "limits": {"input_step_bytes": worker.MAX_STEP_BYTES, "output_step_bytes": worker.MAX_STEP_BYTES,
                     "request_bytes":worker.MAX_REQUEST_BYTES,"vertices":worker.MAX_VERTICES,
                     "scale_min":.001,"scale_max":1000,"axis_ratio_max":1e6},
          "cases": rows}
(RUN/"report.json").write_text(json.dumps(report, indent=2, allow_nan=False))
print(json.dumps({"report": str(RUN/"report.json"), "cases":len(rows), "passed":sum(r["status"]=="passed" for r in rows)},indent=2))
