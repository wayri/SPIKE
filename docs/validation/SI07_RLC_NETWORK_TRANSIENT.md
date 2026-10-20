<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI07-S05 verification: combined series-R/L and shunt-C boundaries

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Verified 18 October 2026. **Done for the bounded stage; experimental,
production-unqualified.** SI07 and complete PI/SI parity remain open.
The [method record](../RLC_NETWORK_TRANSIENT.md) contains the independent
derivation, reviewed primary references, topology, units and limitations.

## Executed evidence

The [canonical source-bound receipt](parity/SI07-S05.json) retains **10 tests,
zero skips** and the actual execution log (unbundled local record: `parity/SI07-S05-rlc-reverified.log`).
Seven numerical tests and three actual worker/schema/example tests executed.
Reproduce into new repository paths:

```powershell
.venv/Scripts/python.exe scripts/parity_pisi_gate.py --stage SI07-S05 --output build/rlc-check.json --log build/rlc-check.log
```

Checks include:

- Independent analytic loaded-RLC under/critical/overdamped voltage/current and
  derivative references, source-work/heat/storage balance, and zero source R
  with passive network damping.
- Coupled two-port physical equations with two inductor and two capacitor states,
  unequal component values, signed PWL forcing, reversed termination request
  order, both derivatives, power, energy and final-state maps.
- A network with genuine nonzero fitted memory: conductance in parallel with an
  inductor, using samples derived from physical admittance. The actual fitter
  executes and recovers the nonzero residue. Independent physical [V,Isrc,In]
  equations check the full [x,q,v] feedback path and three-storage energy balance.
- Mixed pure-R, RL and RC ports compared with existing APIs, including an ideal
  zero-R/zero-L/zero-C voltage row. General constrained circuits are not inferred.
- Output-grid refinement, physical time/L/C scaling and reference-impedance
  invariance at 1, 25, 100 and 1,000 ohms versus 50 ohms.
- Stable active fits admitted; singular, unstable, marginal, malformed,
  precision, resource and cancellation cases fail without successful partial
  output. A 24-memory+8-L+8-C case proves total-state preflight before fitting.
- Actual top-level worker, strict registered schemas, immutable input/source
  identity, boundary retention and an executable original loaded-RLC example.

Preselected acceptance: voltage/current 2e-10 in their SI units, derivatives
2e-8 in their SI units, KVL/KCL 2e-10 V/A and energy balance 1e-9 J.
Across the analytic damping/zero-source-R cases, measured maximum voltage error
was 6.217248937900877e-15 V and source-current error 4.440892098500626e-16 A;
maximum normalized physical/algebraic boundary residual was
4.3027392577434904e-16. Probe retained in `build/si07-s05-analytic-errors.json`.
These are mathematical reference errors, not physical measurement uncertainty.

All **16 earlier PI/SI numerical stages** were actually reexecuted after shared
worker/runner changes. Their canonical receipts retain executed
`*-rlc-reverified.log` records; previous canonical receipts are preserved as
`*-pre-rlc.json`. Failed, stale, incomplete or skipped evidence cannot close a
stage. Bounded mechanical evidence remains independently validated.

Broader focused regressions passed **258 tests**, zero skips/failures/errors,
in 26.000 seconds. They include retained PI/SI, mechanical/thermal, network-graph,
schema catalog and tracking/evidence suites. Log: `build/si07-s05-focused.log`.
Architecture and ten final documentation checks passed, together with 47 final
tracking/schema checks after the roadmap and backlog completion updates.
The full release suite was not rerun. The previous full-Python attempt's
[unresolved provider connection failures](SI07_CAPACITIVE_NETWORK_TRANSIENT.md)
remain outside this stage's numerical evidence. No clean release claim is made.

## Review and limits

Independent read-only numerical review found no actionable defect. It confirmed
the nonzero-memory reference closes the combined fitted-memory/current/voltage
coverage gap and the multiport state-order checks are meaningful. Physical
coupled/memory reference propagation uses separate circuit equations with the
same SciPy exponential dependency; separate analytic scalar cases guard against
an expm-to-expm comparison being the only accuracy evidence.

Source-port identities and separate source/network currents preserve actual
supplied resistor loss and L/C storage for future conservative coupling. This
does not execute thermal transfer, infer material laws or reconstruct physical
storage inside arbitrary fit states. General topology/descriptor/nonlinear
models, mutual boundary components, nonzero initial conditions and steppable
sessions remain open. Floating-point eigenvalue admission is not a robust
stability certificate for arbitrary nonnormal/uncertain systems. Measured
broadband/passivity/causality qualification and knowledgeable human numerical
review before release remain required.
