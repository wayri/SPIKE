# SPDX-License-Identifier: Apache-2.0
"""Fixed FreeCAD worker for checked positive STEP geometry scaling in mm.

Only request.json and source.step in the supervisor-owned directory are input.
No document objects, expressions, scripts, materials or solver claims are read.
The diagonal map acts about the source model origin: x' = diag(scale_xyz) x.
Its determinant multiplies volume and each positive axis scale multiplies both
corresponding bounding-box endpoints. Native tolerances can make even an
admitted scale fail these checks; admission is not a geometry guarantee.
"""
import hashlib
import json
import math
from pathlib import Path

import FreeCAD as App
import Part


MAX_STEP_BYTES = 16 * 1024**2
MAX_REQUEST_BYTES = 4096
MAX_VERTICES = 256
VOLUME_REL_TOL = 1e-8
BOUNDS_ABS_TOL_MM = 2e-6
COORD_REL_TOL = 1e-9


def _read_bounded(path, limit):
    if path.is_symlink() or not path.is_file():
        raise ValueError("STEP scaling requires regular input files.")
    with path.open("rb") as stream:
        payload = stream.read(limit + 1)
    if not payload or len(payload) > limit:
        raise ValueError("STEP scaling input is empty or exceeds its byte budget.")
    return payload


def _request(root):
    request = json.loads(_read_bounded(root / "request.json", MAX_REQUEST_BYTES))
    if not isinstance(request, dict) or set(request) != {"scale_xyz", "source_sha256"}:
        raise ValueError("Invalid STEP scaling request fields.")
    scale = request["scale_xyz"]
    if not isinstance(scale, list) or len(scale) != 3:
        raise ValueError("STEP scale_xyz must contain three positive numbers.")
    if any(isinstance(s, bool) or not isinstance(s, (int, float))
           or not math.isfinite(s) or not 1e-3 <= s <= 1e3 for s in scale):
        raise ValueError("STEP scales must be finite numbers in [1e-3, 1e3].")
    if max(scale) / min(scale) > 1e6:
        raise ValueError("STEP axis scale ratio exceeds 1e6.")
    digest = request["source_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Invalid source SHA-256.")
    source = _read_bounded(root / "source.step", MAX_STEP_BYTES)
    if hashlib.sha256(source).hexdigest() != digest:
        raise ValueError("STEP source SHA-256 does not match the request.")
    return [float(s) for s in scale], digest


def _facts(shape):
    if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1:
        raise ValueError("STEP scaling requires exactly one valid closed solid.")
    solid = shape.Solids[0]
    if not solid.isValid() or not solid.isClosed():
        raise ValueError("STEP scaling requires exactly one valid closed solid.")
    # A compound containing a solid plus a sheet/wire/point is not one solid.
    if any(len(getattr(shape, k)) != len(getattr(solid, k))
           for k in ("Faces", "Edges", "Vertexes")):
        raise ValueError("STEP scaling rejects mixed solid and non-solid geometry.")
    volume = float(solid.Volume)
    box = solid.optimalBoundingBox(False, False)
    bounds = [float(getattr(box, k)) for k in ("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax")]
    if not math.isfinite(volume) or volume <= 0 or any(not math.isfinite(v) for v in bounds):
        raise ValueError("STEP solid has non-finite or non-positive geometric facts.")
    if any(bounds[i + 3] <= bounds[i] for i in range(3)):
        raise ValueError("STEP solid has a degenerate bounding box.")
    vertices = solid.Vertexes
    facts = {"solid_count": 1, "valid": True, "closed": True,
             "volume_mm3": volume, "bounds_mm": bounds,
             "bounds_method": "optimalBoundingBox(False, False)", "vertex_count": len(vertices),
             "vertices_status": "complete" if len(vertices) <= MAX_VERTICES else "omitted_over_limit"}
    if len(vertices) <= MAX_VERTICES:
        points = [[float(v.Point.x), float(v.Point.y), float(v.Point.z)] for v in vertices]
        if any(not math.isfinite(c) for p in points for c in p):
            raise ValueError("STEP solid has non-finite vertices.")
        facts["vertices_mm"] = sorted(points)
    return facts


def _coordinate_close(a, b, absolute):
    return math.isclose(a, b, rel_tol=COORD_REL_TOL, abs_tol=absolute)


def _check_geometry(original, observed, scale, label):
    expected_volume = original["volume_mm3"] * math.prod(scale)
    if not math.isfinite(expected_volume) or not math.isclose(
            observed["volume_mm3"], expected_volume, rel_tol=VOLUME_REL_TOL, abs_tol=0):
        raise ValueError(label + " failed the determinant-scaled volume check.")
    expected_bounds = [v * scale[i % 3] for i, v in enumerate(original["bounds_mm"])]
    # OCC's optimal boxes can include about 1e-7 mm of kernel padding. Extreme
    # scales may exceed this fixed admitted envelope and fail closed.
    if any(not _coordinate_close(a, b, BOUNDS_ABS_TOL_MM)
           for a, b in zip(expected_bounds, observed["bounds_mm"])):
        raise ValueError(label + " failed the positive-scaled bounding-box check.")
    if original["vertex_count"] != observed["vertex_count"]:
        raise ValueError(label + " changed the vertex count.")
    if original["vertices_status"] == observed["vertices_status"] == "complete":
        unmatched = list(observed["vertices_mm"])
        for point in original["vertices_mm"]:
            expected = [v * s for v, s in zip(point, scale)]
            match = next((i for i, p in enumerate(unmatched)
                          if all(math.isclose(a, b, rel_tol=0, abs_tol=1e-8)
                                 for a, b in zip(expected, p))), None)
            if match is None:
                raise ValueError(label + " changed the scaled vertex coordinates.")
            unmatched.pop(match)


def scale_step(root_name):
    """Write scaled.step and facts.json after native and STEP reimport checks.

    root_name is supplied by the fixed process supervisor, never by request
    contents. Exceptions are propagated; facts.json is the success marker.
    """
    root = Path(root_name)
    if any((root / name).exists() or (root / name).is_symlink()
           for name in ("scaled.step", "facts.json")):
        raise ValueError("STEP scaling requires a fresh output directory.")
    scale, source_digest = _request(root)
    source = Part.read(str(root / "source.step"))
    source_facts = _facts(source)
    matrix = App.Matrix()
    matrix.A11, matrix.A22, matrix.A33 = scale
    # transformShape can ignore non-uniform scale unless its extra scale check
    # is enabled. transformGeometry explicitly bakes the affine map into BREP.
    scaled = source.Solids[0].transformGeometry(matrix)
    scaled_facts = _facts(scaled)
    _check_geometry(source_facts, scaled_facts, scale, "Native STEP scaling")
    output = root / "scaled.step"
    scaled.exportStep(str(output))
    output_bytes = _read_bounded(output, MAX_STEP_BYTES)
    roundtrip_facts = _facts(Part.read(str(output)))
    _check_geometry(scaled_facts, roundtrip_facts, [1.0, 1.0, 1.0], "STEP roundtrip")
    _check_geometry(source_facts, roundtrip_facts, scale, "STEP roundtrip from source")
    facts = {"contract": "spike/scaled-step-native/v1", "units": "mm",
             "source_sha256": source_digest,
             "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
             "scale_xyz": scale, "freecad_version": ".".join(App.Version()[:3]),
             "source": source_facts, "scaled": scaled_facts, "roundtrip": roundtrip_facts,
             "tolerances": {"volume_relative": VOLUME_REL_TOL,
                            "bounds_absolute_mm": BOUNDS_ABS_TOL_MM,
                            "coordinate_relative": COORD_REL_TOL,
                            "vertices_absolute_mm": 1e-8},
             "checks": "valid closed solid, determinant volume, axis bounds, bounded vertices, STEP reimport",
             "solver_qualified": False}
    (root / "facts.json").write_text(json.dumps(facts, indent=2, allow_nan=False), encoding="utf-8")
    return facts
