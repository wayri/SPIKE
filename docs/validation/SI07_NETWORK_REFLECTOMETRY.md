<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI07-S10 verification: initialized network-port reflectometry

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Verified 18 October 2026. **Done for the bounded stage; experimental,
production-unqualified.** SI07 and complete PI/SI parity remain open.
The [method ledger](../NETWORK_REFLECTOMETRY.md) retains reviewed primary
instantaneous wave/power physics, independently derived fixed-plane apparent
ratios, units, resolution semantics, conditioning and multiphysics ownership.

## Executed evidence

The [canonical source-bound receipt](parity/SI07-S10.json) retains **9 tests,
zero skips**, and its actual log (unbundled local record: `parity/SI07-S10-reflectometry-reverified.log`).
Six numerical and three actual worker/schema/example tests executed. Reproduce
into new repository paths:

```powershell
.venv/Scripts/python.exe scripts/parity_pisi_gate.py --stage SI07-S10 --output build/reflectometry-check.json --log build/reflectometry-check.log
```

Checks include:

- Independent analytic loaded-RLC physical voltages/currents and known resistor
  mismatch at 100 ohms, plus a separate worker example at 75 ohms. Constant
  apparent resistance and reflection agree while boundary source current differs
  from network current because of external shunt-C current.
- Actual fitted G-parallel-inductor memory against an independently specified
  physical state ODE with nonzero initial current/voltage. Dynamic apparent V/I
  and signed network transport are checked without assigning heat to fit states.
- Coupled two-port conductance/RLC equations with both ports driven and common
  supplied state. Both probe ports and reversed boundary ordering are verified.
- Exactly one actual fitting call and unchanged complete nested initialized
  transient result; original input/digest and fit-bound state identity retained.
- Strict threshold equality, zero incident voltage and null/status consistency;
  admitted open response Gamma=1 keeps impedance unresolved without infinity.
  Stable active Gamma=2, negative apparent resistance of -150 ohms and negative
  transported power remain signed and unclipped.
- Reference impedances 1/25/100/1,000 ohms preserve physical V/I/power/impedance;
  wave/reflection values follow their explicit changed normalization. Time/L/C
  scaling by 0.001 and shared-observation refinement preserve the physical case.
- Unknown/Boolean/nonfinite/extra/missing fields, bad state identity and nonpositive
  floors fail closed; pre-fit aggregate work/full-output budgets reject before
  fitting. Corrupted waves/current and unrepresentable values reject; cancellation
  is exercised before/mid/after actual execution.
- Actual worker, registered strict 2020-12 schemas, executable original example
  and original analytic source. Schema conditionals reject non-null unresolved
  ratios, null resolved ratios and contradictory incident/impedance statuses.

Preset physical V/I acceptance is 2e-10 SI absolute plus 1e-9 relative.
The retained physical G-parallel-L probe measured maximum voltage error
2.7755575615628914e-15 V, current error 2.498001805406602e-16 A, signed power
error 5.412337245047638e-16 W, reflection-ratio error 1.5987211554602254e-14 and
apparent-impedance error 1.4210854715202004e-14 ohms. Its maximum reconstruction
errors were 6.279698983036042e-16 V and 2.7755575615628914e-17 A. One actual
solution retained six resolved samples. Reproduce with
`build/probe_network_reflectometry.py`; output is
`build/si07-s10-reference-errors.json`. These are mathematical verification
errors, not physical measurement or ratio-uncertainty guarantees.

All **21 earlier PI/SI numerical stages** were actually rerun after shared
worker/runner integration. Canonical receipts retain
`*-reflectometry-reverified.log`; prior receipts are archived as
`*-pre-reflectometry.json`. No hash-only refresh replaced test execution.
Broader focused regressions passed **312 tests**, zero skips/failures/errors,
in 43.813 seconds. Log: `build/si07-s10-focused.log`; scope includes
retained PI/SI, structural/thermal, network graphs, public schemas and evidence
tracking guards. The architecture guard passed
(`build/si07-s10-architecture.log`). Ten final documentation checks and 52 final
completion-tracking/schema checks passed after Done updates. Actual logs/counts
are recorded in backlog verification metadata.

Independent read-only review found no actionable issue and independently ran
**31 tests, zero skips**: six reflectometry numerical, three worker/schema/example,
eight initialized numerical, three initialized contract, eight energy numerical
and three energy contract checks. It traced reference-plane current, real wave
normalization, reconstruction, strict resolution, open/active behavior, common
state, multiport identity, budgets, representability and cancellation.

The full release suite was not rerun; previous provider connection failures
remain [unresolved](SI07_CAPACITIVE_NETWORK_TRANSIENT.md). No clean release
qualification is claimed. Human knowledgeable numerical review before release
remains required.

## Scope and cross-domain limits

Ratios are loaded instantaneous values at the fitted-network port and requested
samples. Other drives, boundary loading and common initial state remain active.
Caller floors are absolute numerical gates, not uncertainty estimates or
conditioning guarantees. Isolated S11, frequency impedance, distance/velocity,
spatial impedance reconstruction, instrument/fixture calibration and measured
VNA/TDR correlation remain open.

Signed power enters the network and can charge/release internal storage; it is
not automatically dissipated heat. The same full initialized request can execute
the energy ledger for continuous work, external resistor heat and L/C storage.
This stage performs no sampled-power energy quadrature, material feedback,
thermal deposition or general multiphysics solve. SI07 and full parity remain
incomplete despite this bounded stage being Done.
