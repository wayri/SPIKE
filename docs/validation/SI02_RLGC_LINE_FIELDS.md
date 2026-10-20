<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S04 verification: driven sampled RLGC fields and loss ledger

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Verified 18 October 2026. **Done for this bounded stage; experimental,
production-unqualified.** SI02 and full PI/SI parity remain open.
The [method ledger](../RLGC_LINE_FIELDS.md) retains independent derivation,
units, conditioning, coherent RMS semantics and physical/coupling limits.
Reviewed primary source: Staelin, *Electromagnetics and Applications* (2011),
chapter 8, section 8.3.1, equations (8.3.3)-(8.3.12) and (8.3.16), printed
pages 249-251 ([official MIT text](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf)).
RMS conversion removes the peak-phasor one-half loss factor; average nominal
L/C storage retains .5*C*|V|² and .5*L*|I|². The source's longitudinal-field
warning limits pure-TEM physical applicability. No external code/data was used.

## Executed evidence

The [canonical source-bound receipt](parity/SI02-S04.json) retains **15 tests,
zero skips**, twelve numerical and three actual worker/schema/example checks.
Its actual log (unbundled local record: `parity/SI02-S04-rlgc-fields-reverified.log`) records executed names.
Reproduce into new repository paths:

```powershell
.venv/Scripts/python.exe scripts/parity_pisi_gate.py --stage SI02-S04 --output build/rlgc-fields-check.json --log build/rlgc-fields-check.log
```

- Independent spatial state matrix exponentials with direct physical terminal
  wave boundary solves check complex interior V/I, right-end inward current,
  signed power, separate nominal electric/magnetic storage and local R/G loss.
  These oracles do not use the kernel's traveling-wave or overlap formulas.
- Separate adaptive spatial quadrature checks integrated conductor and dielectric
  heat, signed net input and raw power balance. Production integration is
  analytic; the quadrature is only a verification oracle.
- A matched single Heaviside wave checks analytic RMS transport, average storage,
  attenuation, heat and equal conductor/dielectric partition. Two-sided lossless
  standing waves have exactly zero loss. Exact zero excitation returns zero
  fields/heat, while coherent relative phase changes lossy interference.
- Symmetric opposing short-line waves retain the leading positive dielectric
  loss instead of erasing the small H-J overlap weight. An independent physical
  leading-order expression checks that tiny positive quantity.
- Independent trapezoidal spatial integration at 64..1024 cells converges at
  second order to the analytic ledger. Probe refinement leaves the production
  ledger exactly unchanged. Length/per-unit and incident-amplitude scaling,
  retained parent-network identity and original source/digest are checked.
- DC/unknown/Boolean/nonfinite/malformed/tuple/duplicate/out-of-range inputs,
  grid mismatch, numerical/underflow/conditioning failures, result preflight and
  cancellation reject without clipping or returning a successful partial sweep.
  Preflight is tested before actual parent network execution.
- Actual worker, strict registered 2020-12 schemas, an independently solved
  second spatial V/I and loss-quadrature example, and the executable original
  coherently driven 5-m example are checked.

Preset independent field tolerances are 3e-12 V and 3e-14 A absolute plus
1e-12 relative. Nominal energy uses 1e-21 J/m plus 2e-12 relative; other local
scalar quantities use 2e-14 SI plus 2e-12 relative. Integrated quadrature and
boundary power comparisons use 2e-12 W; matched heat uses 2e-14 W and storage
1e-22 J/m. The worker's separate field oracle uses 2e-11 SI plus 1e-10 relative;
its heat oracle uses 2e-12 W plus 1e-10 relative. Finest trapezoid error must be
below 2e-7 W, with each doubling ratio between 3.9 and 4.1. Production power
admission is 1e-10 times incident/total/absolute-net power scale, with exact zero
for zero scale; residuals are signed and unmodified.

The retained `build/probe_rlgc_fields.py` produces
`build/si02-s04-reference-errors.json`. Maximum spatial-reference errors were
3.025026694190274e-14 V and 4.3322265993428383e-16 A. Each conductor/dielectric
integral differed from independent quadrature by at most 1.1102230246251565e-16 W.
Maximum tested power residual was 4.440892098500626e-16 W. Trapezoid errors at
64/128/256/512/1024 cells were 1.4062612813114939e-5, 3.510621735869357e-6,
8.773428000763417e-7, 2.1931618865433933e-7 and 5.482782783339246e-8 W;
ratios were 4.00573, 4.00143, 4.00036 and 4.00009. The short antiphase witness
retained 6.579736267395441e-30 W dielectric loss with a leading-order relative
discrepancy 1.9761969838327786e-14. These are synthetic effective-circuit errors,
not physical measurement uncertainty or a claim of exact arithmetic.

All **25 earlier PI/SI numerical stages** were actually rerun after shared
worker/runner integration. Canonical receipts reference
`*-rlgc-fields-reverified.log`; earlier receipts remain archived as
`*-pre-rlgc-fields.json`. No hash-only refresh replaced actual execution.
Broader PI/SI, structural/thermal, network, package, schema and evidence checks
passed **407 tests**, zero skips/failures/errors (`build/si02-s04-focused.log`).
Architecture passed (`build/si02-s04-architecture.log`). An existing package
module was three lines over its size guard: only its wrapper signature was
compacted, with no behavior change; all 39 package tests passed separately
(`build/si02-s04-package.log`) and in the broader suite. The initial broader
run exposed its dependent component-admission receipt as stale because exact
source bytes changed. All seven admission tests were actually rerun with zero
skips in the admitted CPython 3.11 native runtime; the new log is
`parity/WF01-S04C2-rlgc-fields-native-reverified.log`, and the prior receipt
is archived as `parity/WF01-S04C2-pre-rlgc-fields.json`. The original failed
broader log remains `build/si02-s04-focused-initial-stale-admission.log`.
The broad suite was rerun against the refreshed evidence; no hash-only refresh
was substituted for native execution. Ten final documentation
checks and 56 completion-tracking/schema checks passed after Done updates.
Actual logs/counts are recorded in backlog verification metadata.

Independent read-only numerical review found no actionable defect and separately
ran **15 tests, zero skips**. Scope and limitations are retained in
`build/si02-s04-independent-review.json` and backlog verification metadata.
Knowledgeable human numerical review before release remains required. Full
release tests were not rerun; prior provider connection failures remain
[unresolved](SI07_CAPACITIVE_NETWORK_TRANSIENT.md). No clean release qualification
is claimed.

## Multiphysics and physical limits

This is a supplied uniform scalar uncoupled effective line. R/G are nonnegative
sampled values and L/C nominal positive constants. Frequencies are independent
positive-frequency coherent RMS steady-state cases; no sweep sum or time-domain
waveform is implied. Nominal circuit storage is not a general dispersive-medium
energy law. Nonnegative sampled R/G and power balance do not establish broadband
causality, physical applicability or measured accuracy.

Conductor-loop and dielectric loss remain separate positive electrical watts,
with named locations and original constitutive/excitation identity. Conductor
heat split, material/volume ownership, conservative thermal deposition and
temperature feedback remain separate. DC/transient fields, general complex
dispersion, coupled conductors/branches/returns/discontinuities, geometry/material
extraction, measured correlation and production qualification remain open.
