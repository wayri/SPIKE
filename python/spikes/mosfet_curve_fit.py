# SPDX-License-Identifier: Apache-2.0
"""Offline, reduced-order forward NMOS DC fitting; never qualification.

Independent derivation: integrate the channel charge proportional to (Vgs-Vto-v)
from v=0 to min(Vds,Vgs-Vto). The resulting current is KP*(u*d-d*d/2)
in triode or KP*u*u/2 in saturation, multiplied by (1+LAMBDA*Vds).
This matches the owned Level-1 channel in src/spikes/dc_solver.cpp for W/L=1,
bulk tied to source, GAMMA=0. A fixed 1e-12 S native off conductance is included.
The analytic parameter Jacobian is continuous across the triode/saturation
boundary. No external implementation, dataset, or copyrighted oracle is used.

Unweighted current-space least squares uses dimensionless VTO and LAMBDA and
log(KP), bounded trust-region fitting, four deterministic starts, and a scaled
Jacobian rank/condition gate. Every fifth lexically sorted unique bias point is
held out, never fitted. This internal holdout is not independent qualification.
No extraction from images/PDF, body-effect, charge, breakdown, reverse bias,
temperature dependence, BSIM or WBG model is inferred. All exports stay drafts.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re

MAX_BYTES = 1024 * 1024
MAX_ROWS = 5000
MIN_ROWS = 15
OFF_CONDUCTANCE_S = 1e-12
LIMITATIONS = (
    "Reduced-order unqualified DC draft, not a manufacturer, BSIM or WBG model.",
    "Forward NMOS only; bulk tied to source and W/L=1; fixed 1e-12 S off conductance.",
    "No fitted capacitance/charge, switching loss, reverse conduction, breakdown or temperature law.",
    "Validity is limited to sampled biases at the declared temperature; bounding box is not full coverage.",
    "Deterministic internal holdout is not independent measured qualification; human review required.",
)


def read_csv(path):
    """Read at most 1 MiB, 5,000 unique SI rows: vgs_v,vds_v,id_a."""
    path = Path(path)
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("CSV must contain 1 byte to 1 MiB")
    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig")), strict=True)
        if next(reader, None) != ["vgs_v", "vds_v", "id_a"]:
            raise ValueError("CSV header must be exactly vgs_v,vds_v,id_a (volts, volts, amperes)")
        rows = []
        seen = set()
        for line, cells in enumerate(reader, 2):
            if len(rows) >= MAX_ROWS:
                raise ValueError("CSV exceeds 5,000 samples")
            if len(cells) != 3:
                raise ValueError(f"CSV line {line}: exactly three SI values required")
            try:
                row = tuple(float(v) for v in cells)
            except ValueError as exc:
                raise ValueError(f"CSV line {line}: numeric SI values required; no unit suffixes") from exc
            if not all(math.isfinite(v) for v in row):
                raise ValueError(f"CSV line {line}: all values must be finite")
            if not (0 <= row[0] <= 100 and 0 <= row[1] <= 10000 and 0 <= row[2] <= 100000):
                raise ValueError(f"CSV line {line}: require 0<=Vgs<=100 V, 0<=Vds<=10,000 V, 0<=Id<=100,000 A")
            if row[:2] in seen:
                raise ValueError(f"CSV line {line}: duplicate bias; aggregate replicates explicitly before import")
            seen.add(row[:2]); rows.append(row)
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("CSV must be well-formed UTF-8 text") from exc
    if len(rows) < MIN_ROWS:
        raise ValueError("At least 15 unique samples required for fitting and internal holdout")
    return sorted(rows), hashlib.sha256(raw).hexdigest()


def current_and_jacobian(vgs, vds, parameters):
    """Vectorized Id [A] and dId/d(VTO [V], KP [A/V2], LAMBDA [1/V])."""
    import numpy as np
    vto, kp, lam = parameters
    gate = np.asarray(vgs, dtype=float); drain = np.asarray(vds, dtype=float)
    u = np.maximum(gate - vto, 0)
    d = np.minimum(drain, u)
    area = u*d - 0.5*d*d
    modulation = 1 + lam*drain
    channel = kp*area
    jac = np.column_stack((-kp*d*modulation, area*modulation, channel*drain))
    return channel*modulation + OFF_CONDUCTANCE_S*drain, jac


def _metrics(actual, predicted):
    import numpy as np
    error = predicted - actual
    scale = max(float(np.max(np.abs(actual))), 1e-15)
    return dict(samples=len(actual), rmse_a=float(np.sqrt(np.mean(error*error))),
                max_absolute_error_a=float(np.max(np.abs(error))),
                normalized_rmse=float(np.sqrt(np.mean(error*error)) / scale),
                normalization="maximum absolute measured current in this subset; floor 1e-15 A")


def fit_csv(path, *, temperature_k=298.15, source_kind="measured", source_note=""):
    """Return a JSON-safe review report. No model package is auto-qualified."""
    import numpy as np
    from scipy.optimize import least_squares
    if isinstance(temperature_k, bool) or not isinstance(temperature_k, (float, int)) or not math.isfinite(temperature_k) or not 200 <= temperature_k <= 600:
        raise ValueError("Declare one finite measurement temperature between 200 and 600 K")
    if source_kind not in ("measured", "datasheet_table"):
        raise ValueError("Source kind must be measured or datasheet_table; image extraction is unsupported")
    if not isinstance(source_note, str) or len(source_note) > 2000 or "\x00" in source_note:
        raise ValueError("Source note must be text of at most 2,000 characters")
    rows, digest = read_csv(path)
    data = np.asarray(rows)
    heldout = np.arange(len(rows)) % 5 == 4
    train = data[~heldout]
    if len(np.unique(train[:, 0])) < 3 or len(np.unique(train[:, 1])) < 3:
        raise ValueError("Training data needs at least three distinct Vgs and Vds values")
    gs = max(float(train[:, 0].max()), 1e-3)
    ds = max(float(train[:, 1].max()), 1e-3)
    scale = float(train[:, 2].max())
    if scale <= 1e-12 or np.count_nonzero(train[:, 2] > 1e-12) < 6:
        raise ValueError("At least six conducting training points above 1e-12 A are required")
    lower = [0, math.log(1e-12), 0]
    upper = [1-1e-9, math.log(1e6), 10*ds]

    def unpack(x):
        return (float(x[0]*gs), float(np.exp(x[1])), float(x[2]/ds))

    def residual(x):
        return (current_and_jacobian(train[:, 0], train[:, 1], unpack(x))[0]-train[:, 2])/scale

    def jacobian(x):
        params = unpack(x)
        return current_and_jacobian(train[:, 0], train[:, 1], params)[1] * np.array([gs, params[1], 1/ds])/scale

    fits = []
    for threshold in (0.02, 0.25, 0.5, 0.8):
        kp = min(max(2*scale / (gs*(1-threshold))**2, 1e-11), 1e5)
        fit = least_squares(residual, [threshold, math.log(kp), 0.01], jac=jacobian,
                            bounds=(lower, upper), x_scale="jac", max_nfev=400,
                            ftol=1e-11, xtol=1e-11, gtol=1e-11)
        if fit.success and np.all(np.isfinite(fit.x)):
            fits.append(fit)
    if not fits:
        raise ValueError("Bounded fit did not converge; no model was generated")
    fit = min(fits, key=lambda value: float(np.dot(value.fun, value.fun)))
    jac = jacobian(fit.x)
    norms = np.linalg.norm(jac, axis=0)
    if np.any(norms < 1e-12):
        raise ValueError("Parameters are not identifiable from these biases; include conducting transfer/output sweeps")
    singular = np.linalg.svd(jac / norms, compute_uv=False)
    condition = float(singular[0] / max(singular[-1], 1e-300))
    if condition > 1e8:
        raise ValueError("Fit is ill-conditioned; provide more independent transfer/output biases")
    params = unpack(fit.x)
    predicted, _ = current_and_jacobian(data[:, 0], data[:, 1], params)
    training = _metrics(data[~heldout, 2], predicted[~heldout])
    validation = _metrics(data[heldout, 2], predicted[heldout])
    warnings = list(LIMITATIONS)
    if max(training["normalized_rmse"], validation["normalized_rmse"]) > .05:
        warnings.append("Fit/holdout normalized RMSE exceeds 5%; model mismatch or data issues require review.")
    if np.any(fit.active_mask):
        warnings.append("At least one fitted parameter is at a search bound; parameters may not be identifiable.")
    return dict(contract="spikes/mosfet-dc-fit/v1", status="unqualified_draft",
                parameters=dict(VTO=params[0], KP=params[1], LAMBDA=params[2]),
                parameter_units=dict(VTO="V", KP="A/V^2 (effective W/L=1)", LAMBDA="1/V"),
                source=dict(path=str(Path(path).resolve()), sha256=digest, kind=source_kind,
                            note=source_note, extraction="human-supplied SI CSV; no image extraction"),
                validity=dict(vgs_v=[float(data[:, 0].min()), float(data[:, 0].max())],
                              vds_v=[float(data[:, 1].min()), float(data[:, 1].max())],
                              temperature_k=float(temperature_k), bulk="source-tied", width_over_length=1.0),
                fit_metrics=training, heldout_metrics=validation,
                algorithm=dict(method="bounded trust-region analytic-Jacobian current least squares", starts=4,
                               max_evaluations_per_start=400, selected_evaluations=int(fit.nfev),
                               scaled_jacobian_condition=condition,
                               split="every fifth sorted unique (Vgs,Vds) bias held out", version=1),
                warnings=warnings,
                points=[dict(vgs_v=g, vds_v=d, id_a=i, fitted_id_a=float(p), heldout=bool(h))
                        for (g, d, i), p, h in zip(rows, predicted, heldout)])


def model_card(report, name="FITTED_NMOS", *, reviewed=False):
    """Create a draft card only after an explicit caller/user review."""
    if reviewed is not True:
        raise ValueError("Review the fit, holdout, provenance and limitations before export or placement")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
        raise ValueError("Model name must be 1-64 ASCII letters/digits/underscores, starting with letter/underscore")
    if report.get("contract") != "spikes/mosfet-dc-fit/v1" or report.get("status") != "unqualified_draft":
        raise ValueError("Expected an unqualified MOSFET DC fit report")
    p = report["parameters"]
    values = [p[key] for key in ("VTO", "KP", "LAMBDA")]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values):
        raise ValueError("Model parameters must be finite numbers")
    if not (0 <= p["VTO"] <= 100 and 1e-12 <= p["KP"] <= 1e6 and 0 <= p["LAMBDA"] <= 10):
        raise ValueError("Model parameters exceed the fitting bounds")
    # Full report preserves source, sample residuals and limitations alongside exports.
    return ("* UNQUALIFIED reduced-order forward DC fit; W/L=1, bulk tied to source.\n"
            "* No fitted charge, temperature law, breakdown, BSIM or WBG qualification.\n"
            f".model {name} NMOS (LEVEL=1 VTO={p['VTO']:.17g} KP={p['KP']:.17g} "
            f"LAMBDA={p['LAMBDA']:.17g} GAMMA=0)\n")


def main():
    """Bounded subprocess interface: path and JSON options in argv; JSON stdout."""
    import sys
    try:
        result = fit_csv(sys.argv[1], **json.loads(sys.argv[2]))
        print(json.dumps(result, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
