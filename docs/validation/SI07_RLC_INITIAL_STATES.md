<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI07-S06 verification: supplied RLC initial states and continuation

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Verified 18 October 2026. **Done for the bounded stage; experimental,
production-unqualified.** SI07 and complete PI/SI parity remain open.
The [method record](../RLC_INITIAL_STATES.md) contains the independent derivation,
reviewed primary sources, initialization/binding semantics and limitations.

## Executed evidence

The [canonical source-bound receipt](parity/SI07-S06.json) retains **11 tests,
zero skips**, and the final execution log (unbundled local record: `parity/SI07-S06-ramp-reverified.log`).
Eight numerical and three actual worker/schema/example tests executed. Reproduce
into new repository paths:

```powershell
.venv/Scripts/python.exe scripts/parity_pisi_gate.py --stage SI07-S06 --output build/initialized-check.json --log build/initialized-check.log
```

Checks include:

- Analytic free and forced under/critical/overdamped loaded-RLC trajectories
  with signed initial capacitor voltage and inductor current, including both
  derivatives and original supplied-state provenance.
- Physically derived nonzero fitted memory for a conductance/inductor network;
  independent physical equations and initial-energy+source-work=heat+final-energy
  balance, including known internal inductor storage only in the reference.
- Explicit PWL chunk continuation at a waveform knot (0.35 s), on a nonzero ramp
  at an existing observation (0.5 s), and on that ramp between observations
  (0.47 s). Check supplied restart continuity, all shared later observations and
  final fitted memory plus physical I/V states.
- Source-horizon restart when observations end earlier, coupled multiport
  ordering, reference-impedance/physical-time invariance and exact zero-state
  equivalence with v1. The original public API rejects an initial-state keyword.
- Fit-digest/shape/subset/value/resource admission before fitting, unsupported
  normalization ranges, cancellation in shared propagation and final adapter
  polling, registered schemas and the executable charged/energized example.

Preselected acceptance: voltage/current 2e-10 in SI units, derivatives 2e-8 in
SI units, integrated energy balance 1e-9 J. Across analytic initialized damping
cases, maximum errors were 1.9984014443252818e-15 V and
2.0469737016526324e-16 A. At the unobserved 0.47 s split on a nonzero ramp,
retained-observation differences were at most 1.1796119636642288e-15 V and
6.938893903907228e-17 A. Final differences were 1.6653345369377348e-16 V and
1.214306433183765e-17 A. Actual probe:
`build/si07-s06-analytic-errors.json`. These are mathematical reference errors,
not physical measurement uncertainty or a broadband device accuracy claim.

All **17 earlier PI/SI numerical stages** were actually rerun after the shared
worker/runner changes and narrow RLC propagator refactor. Canonical receipts
retain `*-initial-reverified.log`; previous receipts are preserved as
`*-pre-initial.json`. The final SI07-S06 receipt separately binds the corrected
nonzero-ramp coverage; its preceding receipt is archived as
`SI07-S06-pre-ramp.json`. No source hash was refreshed without actual execution.

Broader focused regressions passed **270 tests**, zero skips/failures/errors,
in 30.531 seconds. Log: `build/si07-s06-focused.log`; scope includes retained
PI/SI, mechanical/thermal, network graphs, schemas and evidence/tracking guards.
Architecture and ten final documentation checks passed, together with 48 final
tracking/schema checks after roadmap/backlog completion updates. The full release
suite was not rerun; previous full-Python provider connection failures remain
[unresolved](SI07_CAPACITIVE_NETWORK_TRANSIENT.md). No clean release claim is made.

## Review and limits

Independent read-only review found no actionable defect or material coverage gap,
including after correcting a plateau split to actual nonzero-ramp cases. Review
confirmed pre-fit state admission, normalization, original v1 behavior, actual
source-horizon final state and exact PWL continuation semantics.

The state record has no clock and binds neither code revision, boundaries nor
source history. Changed parameters/forcing specify a new initial-value problem;
no automatic conservative energy transfer across such changes is established.
The fit request binds memory coordinates, without authenticating supplied values
or assigning generic physical fit-state energy. Managed sessions, accepted-step/
rollback, general DAE/nonlinear models and thermal integration remain open.
Physical reference propagation shares the existing exponential dependency, with
separate analytic scalar cases providing independent trajectory checks.
Measured validation and knowledgeable human numerical review before release
remain required.
