<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI07-S04 verification: mixed resistive/shunt-capacitive network transients

Verified 18 October 2026. **Done for the bounded stage; experimental,
production-unqualified.** SI07 and complete PI/SI parity remain open.
The [method record](../CAPACITIVE_NETWORK_TRANSIENT.md) contains the independent
derivation, reviewed primary sources, API, units and admission limits.

## Executed evidence

The [canonical source-bound receipt](parity/SI07-S04.json) retains **11 tests,
zero skips** and the [actual execution log](parity/SI07-S04-capacitive-reverified.log).
Eight numerical tests and three actual worker/schema/example tests executed.
Reproduce into new repository paths:

```powershell
.venv/Scripts/python.exe scripts/parity_pisi_gate.py --stage SI07-S04 --output build/capacitive-check.json --log build/capacitive-check.log
```

Checks include:

- Analytic RC and under/critical/overdamped parallel-RLC responses, derived from
  component laws and charge conservation; actual supplied-pole fitting executes.
- Signed PWL forcing, output-grid refinement and integrated source-work,
  resistor-dissipation and physical-reference stored-energy balance.
- Mixed capacitor/resistor ports, ideal zero-R/zero-C voltage rows, and a coupled
  two-port with two positive capacitors, unequal R/C and reversed termination
  request order. Independent physical admittance equations check cross-coupling.
- Separate source/network currents, capacitor voltage and derivative, physical
  KCL and algebraic residuals, actual R*Isource^2 loss and C*V^2/2 energy.
- Physical time/C/L scaling and reference-impedance invariance at 1, 25, 100 and
  1,000 ohms versus 50 ohms.
- Stable active fits retained; singular, unstable, marginal, malformed,
  precision, resource and cancellation cases fail without successful partial output.
  Capacitor states count toward the 32-state/48-augmented limits before fitting.
- Top-level worker dispatch, strict registered public schemas, immutable input/
  source identity and an executable original RC example.

Preselected numerical acceptance: voltage 2e-11 V, current 2e-11 A, derivative
2e-9 V/s, KCL 2e-10 A and integrated energy balance 1e-10 J. The separate
microsecond RC worker example uses 2e-8 V/s absolute derivative tolerance.
Across the three analytic damping cases, measured maximum errors were
3.9968028886505635e-15 V, 5.551115123125783e-16 A and
3.5349501104064984e-13 V/s; maximum normalized KCL/mixed-row residual was
2.2598131332490492e-15. These are mathematical reference errors, not measurement
uncertainty or a broadband physical accuracy guarantee.

All **15 prior PI/SI numerical stages** were actually rerun after shared worker
and runner changes. Their canonical receipts retain new executed
`*-capacitive-reverified.log` records; prior canonical receipts are archived as
`*-pre-capacitive.json`. Failed, skipped or stale evidence cannot close a stage.
Existing bounded mechanical evidence remains separately validated.

Broader focused regressions passed **247 tests**, zero skips/failures/errors,
in 22.250 seconds: retained PI/SI, mechanical/thermal, network-graph, schema and
tracking/evidence suites. Actual log: `build/si07-s04-focused.log`. Architecture
checks passed, as did ten documentation files and 46 final tracking/schema checks.
Full Python discovery was attempted, then interrupted after unrelated
assistant-provider loopback/connection failures; no complete or clean full-suite
result is claimed. Log: `build/si07-s04-full-python-writable-temp.log`.
`test_models_and_status_do_not_probe_implicitly` reproduced independently with
`ProviderError: Provider connection failed`; retained traceback:
`build/si07-s04-full-provider-blocker.log`. The cause of that connection failure
was not diagnosed in this numerical stage. An earlier default-temp attempt hit
sandbox temporary-directory permissions and was superseded with a writable
temporary directory outside the repository. No acceptance oracle was weakened.
Full release qualification remains open.

## Review and remaining limits

Independent read-only numerical review found no actionable formulation or
implementation defect. Its requested two-positive-capacitor coupled-port oracle
was added and passed. This does not replace knowledgeable human numerical review
required before release. Eigenvalue/relative-margin admission is a floating-point
diagnostic, without a robust stability certificate for arbitrary nonnormal or
uncertain systems.

This stage supports supplied finite series R with shunt C, mixed with pure-R
ports, zero initial states and regular resolved stable closure. Combined general
RLC/nonlinear/descriptor boundaries, arbitrary initial conditions, steppable
sessions and thermal-mesh coupling remain open. Histories retain quantities and
identities needed for later coupling; they do not implement heat transfer or
physical energy reconstruction for generic fitted-network states. Measured
correlation, causality/passivity and fit-band uncertainty remain separate gates.
