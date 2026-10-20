<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI07-S03 verification: mixed resistive/series-inductive network transients

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Verified 18 October 2026. **Done for the bounded stage; experimental,
production-unqualified.** This does not complete SI07 or the PI/SI stack.
The [method record](../INDUCTIVE_NETWORK_TRANSIENT.md) gives the independent
derivation, reviewed primary references, API and unsupported cases.

## Executed evidence

The [canonical source-bound receipt](parity/SI07-S03.json) retains **11 tests,
zero skips** and the actual execution log (unbundled local record: `parity/SI07-S03-inductive-reverified.log`).
Eight numerical tests and three actual worker/schema/example tests executed.
Reproduce into new repository paths:

```powershell
.venv/Scripts/python.exe scripts/parity_pisi_gate.py --stage SI07-S03 --output build/inductive-check.json --log build/inductive-check.log
```

Checks include:

- Under/critical/overdamped series RLC step references, derived directly from
  KVL and ideal component laws; actual supplied-pole fitting executes first.
- Signed PWL forcing compared with independent physical capacitor-voltage/
  inductor-current equations and observation-grid invariance.
- Mixed resistor/RL coupled through ports with reversed supplied boundary order,
  and two simultaneous inductors driving a coupled-capacitance two-port network.
- Voltage/current/derivative, KVL residual, supplied resistor loss and inductor
  energy, plus independently integrated source-work/storage/dissipation balance.
- Physical time/L/C scaling and unchanged physical trajectories when the same
  capacitor network is re-encoded at Z0=1,25,100,1000 ohms versus 50 ohms.
- Stable active fitted data retained; singular, unstable, marginal/lossless,
  malformed, floating-point, resource and cancellation cases rejected.
- Top-level worker dispatch, registered public request/result schemas, original
  source/boundary/input-digest retention and the executable original RLC example.

Tolerances were fixed before acceptance: voltage 2e-11 V, current 1e-11 A,
derivative/KVL 2e-10 in corresponding SI units and energy balance 1e-11 J.
Across the three analytic damping cases, the measured maximum voltage error was
1.9984014443252818e-15 V and current error 1.5005358067199381e-16 A; maximum
normalized boundary residual was 2.220446049250313e-16. These are mathematical
reference errors, not a physical measurement uncertainty or broadband guarantee.

All **14 prior PI/SI numerical stages** were actually rerun after shared worker
and runner changes. Their canonical receipts now point to executed
`*-inductive-reverified.log` records; prior canonical receipts are preserved as
`*-pre-inductive.json`. Failed/skipped/stale/incomplete evidence cannot close a
stage. Existing bounded mechanical evidence remains separately validated.

Broader focused regression execution passed **235 tests**, zero skips/failures/
errors, in 27.453 seconds. It covered the retained PI/SI numerical suites,
mechanical/thermal contracts, network graphs, schema catalog and tracking/evidence
guards; log: `build/si07-s03-focused.log`. Architecture and eight relevant
documentation checks passed. Final tracking/documentation updates receive
separate focused checks. Full release tests were not rerun; prior unrelated
full-suite failures remain outside this stage's evidence.

## Review and remaining limits

An independent read-only agent review found no actionable formulation or
implementation defect. Its requested reference-impedance invariance test was
added and passed. Agent review does not replace knowledgeable human numerical
review required before release. The eigenvalue/relative-margin check is a
floating-point admission diagnostic, without a robust stability certificate for
arbitrary highly nonnormal systems or uncertain parameters.

Supported boundaries are finite, supplied nonnegative series R/L, with at least
one positive L, zero initial states and a regular resolved asymptotically stable
connected model. Capacitive/nonlinear/general-circuit or descriptor boundaries,
arbitrary initial states, a steppable session, physical fit-state energy and
thermal-mesh integration remain open. Returned power/storage describe only the
explicit supplied boundary components. Source causality/passivity, measurement
correlation, fit-band/extrapolation uncertainty and complete SI waveform/eye/TDR
qualification remain open.
