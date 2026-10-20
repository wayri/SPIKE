<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S01 verification: distributed lossless TEM line transient

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Verified 18 October 2026. **Done for the bounded stage; experimental,
production-unqualified.** SI02 and complete PI/SI parity remain open.
The [method ledger](../LOSSLESS_LINE_TRANSIENT.md) retains reviewed primary
telegrapher/reflection physics, independently derived finite causal waves,
units, zero-history assumptions, conditioning/resources and coupling ownership.

## Executed evidence

The [canonical source-bound receipt](parity/SI02-S01.json) retains **10 tests,
zero skips**, and its actual log (unbundled local record: `parity/SI02-S01-lossless-line-reverified.log`).
Seven numerical and three actual worker/schema/example tests executed.
Reproduce into new repository paths:

```powershell
.venv/Scripts/python.exe scripts/parity_pisi_gate.py --stage SI02-S01 --output build/lossless-line-check.json --log build/lossless-line-check.log
```

Checks include:

- Analytic matched finite-ramp propagation, interior fractional delays, exact
  pre-arrival zero waves and unchanged zero initial history.
- Independent separated even/odd geometric round-trip series for mismatched
  resistive ends, repeated echoes and simultaneous two-end PWL excitation.
  This oracle does not use the production alternating-boundary recursion.
- Ideal zero-R finite-horizon full reflections with zero resistor loss, signed
  rightward current/power, opposite terminal current orientations and raw KVL.
- Local electric/magnetic energy checked against the traveling-wave identity.
  A complete matched finite triangular pulse is integrated spatially using
  four Gaussian probes and independently compared with analytic injected work.
  This test does not add a production continuous energy-integral API.
- Impedance and L/C scaling, simultaneous physical time scaling and doubled
  length verify voltage/current/power/energy units and scaled arrival times.
  Additional observations preserve shared samples exactly in the reference case.
- Original request/digest, named probe ordering, supplied source/constitutive
  identity, derived impedance/delay/speed and terminal ownership are retained.
- Malformed/Boolean/nonfinite/duplicate/out-of-range quantities, nonzero source
  start, incompatible horizons and nonincreasing/outside observations reject.
  Unrepresentable interpolation/products, tiny physical constants and excessive
  bounce depth fail closed. Aggregate work/output limits precede wave evaluation;
  cancellation is tested before/during/after bounce execution.
- Actual top-level worker, strict registered 2020-12 schemas, source immutability
  and executable original 5-m line example. A separate closed-form 25/100-ohm
  reflection series checks the example's waves, V/I, power and local energy.

Preset physical V/I tolerance is 2e-10 SI absolute plus 1e-9 relative.
Independent density checks use 1e-14 J/m plus 1e-9 relative (the separate worker
example uses a tighter 1e-20 J/m absolute floor); integrated pulse energy uses
1e-20 J plus 1e-9 relative. The retained echo-reference probe measured maximum
voltage error 1.1102230246251565e-16 V, current error 1.734723475976807e-18 A
and local-energy-density error 6.462348535570529e-27 J/m. Spatial pulse energy
was 1.3333333333333307e-11 J versus analytic injected work
1.3333333333333334e-11 J, differing by 2.7464981276174747e-26 J.
The example's preflight depth was 8, estimated work 38880 and maximum KVL
residual 1.1102230246251565e-16 V. Reproduce with
`build/probe_lossless_line.py`; output `build/si02-s01-reference-errors.json`.
These are ideal-model mathematical errors, not physical measurement uncertainty.

All **22 earlier PI/SI numerical stages** were actually rerun after shared
worker/runner integration. Canonical receipts retain
`*-lossless-line-reverified.log`; earlier receipts remain archived as
`*-pre-lossless-line.json`. No hash-only refresh replaced test execution.
Broader focused regressions passed **323 tests**, zero skips/failures/errors,
in 65.828 seconds. Log: `build/si02-s01-focused.log`; scope includes
retained PI/SI, structural/thermal, network graphs, schemas and evidence guards.
Architecture passed (`build/si02-s01-architecture.log`). Ten final documentation
checks and 53 final completion-tracking/schema checks passed after Done updates.
Actual logs/counts are recorded in backlog verification metadata.

Independent read-only numerical review found no actionable issue and
independently ran **10 tests, zero skips**. Its detailed scope is retained
in `build/si02-s01-independent-review.json` and backlog verification metadata.
Human knowledgeable numerical review before release remains required.
The full release suite was not rerun; previous provider connection failures
remain [unresolved](SI07_CAPACITIVE_NETWORK_TRANSIENT.md). No clean release
qualification is claimed.

## Scope and multiphysics limits

The model is one supplied uniform nondispersive lossless two-conductor TEM line,
with finite nonnegative resistive ends, continuous PWL zero-start sources and
zero distributed history. Exact retarded-time ordering uses fractions of the
admitted binary64 time/position/derived-delay values; this does not remove
physical parameter uncertainty or binary64 arithmetic error in amplitudes.
Bounds and precision rejection remain in force even when a finite ideal model
has a mathematical solution.

Named positions, line parameters, signed terminal power/current and local stored
energy preserve later cross-domain identity. J/m is stored energy, not heat.
Distributed resistive/dielectric losses are zero by assumption; only explicit
terminal resistors report dissipation. Whole-line continuous work/storage,
thermal deposition, material feedback, nonzero history, lossy/dispersive or
multiconductor/branched models, geometry/return/discontinuity extraction and
measured qualification remain separate. SI02 and full parity are incomplete.
