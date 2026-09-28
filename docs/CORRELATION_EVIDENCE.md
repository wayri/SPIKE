<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Solver correlation evidence

`scripts/validate_correlation_manifest.py` checks a versioned
`spike/correlation-evidence-manifest/v1` file. The manifest names one each of
`analytical`, `independent_solver`, and `measured` evidence, using canonical
manifest-relative paths and SHA-256 digests. Each quantity declares a unit,
absolute/relative tolerance, and (for a declared qualified measurement) an
uncertainty with confidence. Solver evidence declares the independent engine
name, version, provenance, and artifact digest. Missing evidence must have an
explicit reason. See `tests/python/test_correlation_manifest.py` for a
synthetic contract fixture, **not** engineering correlation data.

```powershell
python scripts/validate_correlation_manifest.py path/to/manifest.json
```

The manifest is limited to 8 MiB. Exit 0 means *metadata complete*, exit 2
means evidence explicitly missing/unqualified, and exit 1 means invalid or
tampered metadata. The report always marks numerical correlation and solver
sign-off false: this checker does not parse Touchstone/TDR values, align port
or reference-plane definitions, interpolate frequencies, compare uncertainties,
or certify a solver. No measured case is currently admitted by this document.
`examples/correlation/uniform_sheet/` is a hash-bound analytical seed. Its
test evaluates the physical expression independently and confirms that the
missing independent and measured entries keep the report incomplete.

Candidate public sources for a first independently reviewed fixture are
[the open KiCad/TDR sampling-mesh-monitor project](https://github.com/jaseg/sampling-mesh-monitor)
and [NIST's on-wafer S-parameter calibration dataset](https://data.nist.gov/od/id/mds2-3404).
The former is PCB-relevant but needs stackup/calibration and license review
before copying data; the latter is metrologically valuable but is not a PCB
channel. Both require explicit geometry, ports, material, calibration,
uncertainty, and redistribution admission before numerical comparison.
