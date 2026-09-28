# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Digest-bound measured-data admission and explicitly scoped CFD comparisons."""
import hashlib
import math
from pathlib import Path
import numpy as np

NASA_CF_SHA256 = "cd9b6434b7956bc58e859de6af654cd7f891e25303babf1dd8633d6c58f74276"
NASA_CF_URL = "https://tmbwg.github.io/turbmodels/Backstep_validation/cf.exp.dat"
REFERENCE_ID = "NASA-TMR-Driver-Seegmiller-2DBFS-Cf-20151017"


def admit_nasa_backstep_cf(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024*1024:
        raise ValueError("Missing, linked or oversized measured reference")
    payload = path.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != NASA_CF_SHA256:
        raise ValueError("Measured reference digest mismatch")
    rows = []
    for line in payload.decode("ascii").splitlines():
        if not line.strip() or line.startswith(("#", "variables=")):
            continue
        row = list(map(float, line.split()))
        if len(row) != 3 or not all(math.isfinite(v) for v in row) or row[2] <= 0:
            raise ValueError("Invalid measured Cf row")
        rows.append(row)
    if len(rows) < 3 or np.any(np.diff(np.asarray(rows)[:, 0]) <= 0):
        raise ValueError("Measured positions must increase")
    return {"contract": "spike/cfd-measured-reference/v1", "reference_id": REFERENCE_ID,
        "source_url": NASA_CF_URL, "source_sha256": actual,
        "citation": "Driver and Seegmiller (1985), DOI:10.2514/3.8890; NASA TMR corrected Cf table 2015-10-17",
        "coordinates": "x/H; step height H", "observable": "bottom-wall skin-friction coefficient Cf",
        "normalization": "Upstream center-channel reference near x/H=-4, as specified by NASA TMR",
        "reference_reynolds_h": 36000, "opposite_wall_angle_deg": 0,
        "published_error_interpretation": "As supplied; confidence level/covariance not inferred",
        "observations": [{"x_over_h": x, "cf": cf, "published_error": error} for x,cf,error in rows],
        "status": "reference_admitted", "solver_comparison_completed": False,
        "production_qualified": False}


def compare_backstep_cf(reference_path, prediction, *, maximum_absolute_error):
    reference = admit_nasa_backstep_cf(reference_path)
    return _compare_admitted(reference, prediction, maximum_absolute_error=maximum_absolute_error)


def _compare_admitted(reference, prediction, *, maximum_absolute_error):
    """Compare declared same-case predictions; never manufacture CFD outputs.

    Published error bars are descriptive bands, not an assumed confidence
    distribution. The acceptance budget must be chosen before observing error.
    """
    if reference.get("reference_id") != REFERENCE_ID or reference.get("source_sha256") != NASA_CF_SHA256:
        raise ValueError("Unrecognized measured reference identity")
    required = {"reference_id", "reference_sha256", "solver_run_sha256", "reference_reynolds_h",
                "opposite_wall_angle_deg", "x_over_h", "cf", "normalization"}
    if not isinstance(prediction, dict) or set(prediction) != required:
        raise ValueError("Incomplete or unknown prediction fields")
    if prediction["reference_id"] != REFERENCE_ID or prediction["reference_sha256"] != NASA_CF_SHA256:
        raise ValueError("Prediction/reference identity mismatch")
    digest = prediction["solver_run_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("A solver-run artifact digest is required")
    if prediction["reference_reynolds_h"] != 36000 or prediction["opposite_wall_angle_deg"] != 0 or prediction["normalization"] != reference["normalization"]:
        raise ValueError("Prediction case or normalization mismatch")
    if type(maximum_absolute_error) not in (int, float) or not math.isfinite(maximum_absolute_error) or not 0 < maximum_absolute_error < 1:
        raise ValueError("Explicit finite Cf error budget required")
    for key in ("x_over_h", "cf"):
        raw = prediction[key]
        if not isinstance(raw, list) or not 3 <= len(raw) <= 100000 or any(type(v) not in (int, float) for v in raw):
            raise ValueError("Prediction arrays require bounded numeric lists, not booleans")
    try:
        x, cf = (np.asarray(prediction[key], dtype=float) for key in ("x_over_h", "cf"))
    except (OverflowError, ValueError) as exc:
        raise ValueError("Unrepresentable prediction sample") from exc
    if x.ndim != 1 or x.shape != cf.shape or not 3 <= len(x) <= 100000 or not np.isfinite(x).all() or not np.isfinite(cf).all() or np.any(np.diff(x) <= 0):
        raise ValueError("Prediction samples must be finite, aligned and ordered")
    rows = reference["observations"]
    coordinates = np.array([r["x_over_h"] for r in rows])
    if x[0] > coordinates[0] or x[-1] < coordinates[-1]:
        raise ValueError("Prediction does not cover every measurement; no extrapolation")
    values = np.interp(coordinates, x, cf)
    error = values - np.array([r["cf"] for r in rows])
    max_error = float(np.max(np.abs(error)))
    # Scaled RMS avoids overflow when a divergent solver emits large finite Cf.
    rms_error = max_error * float(np.sqrt(np.mean((error / max_error)**2))) if max_error else 0.0
    return {"contract": "spike/cfd-measured-comparison/v1", "status": "compared",
        "reference_id": REFERENCE_ID, "reference_sha256": NASA_CF_SHA256, "solver_run_sha256": digest,
        "sample_count": len(rows), "maximum_absolute_error": max_error,
        "rms_error": rms_error, "declared_absolute_error_budget": maximum_absolute_error,
        "within_declared_budget": max_error <= maximum_absolute_error,
        "within_published_error_bars": int(np.count_nonzero(abs(error) <= [r["published_error"] for r in rows])),
        "interpolation": "linear prediction to measurement positions; no extrapolation",
        "production_qualified": False,
        "limitations": ["Caller must verify solver artifact digest, geometry, boundary conditions, convergence and normalization.",
            "This numerical comparison does not establish enclosure thermal accuracy or statistical confidence."]}
