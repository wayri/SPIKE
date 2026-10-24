<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI08 full-family closure campaign

Started 24 October 2026 at the owner's request to close complete families.
SI08 is the first campaign because its network-data boundary is self-contained;
PI03 physical placement and PI04 switching qualification depend on larger open
geometry, package and device-model work. None of these families is complete.
PI01-S02 board acceptance remains active and its frozen tolerances remain in force.

The original SI08 target is retained: reviewed causality/resampling/DC policy,
calibrated fixture removal, general port pairing and passive causal broadband
model fitting. The table is a family-level acceptance checklist, not a
percentage based on completed implementation milestones.

| Requirement | Current evidence | Remaining closure evidence |
| --- | --- | --- |
| General named pairing and interoperability | SI08-S01 explicit general mixed-mode pairing | End-to-end source/export identity, polarity, permutation, unpaired ports and independent reference checks in the family campaign |
| Source causality and resampling/DC policy | SI08-S03 explicit interpolation/DC and SI08-S04 causal constructed realization | Independent causal delayed/resonant and noncausal references, finite-band ambiguity, missing DC, grid refinement and reviewed applicability policy |
| Coupled multiport fixture algebra | Verified supplied 2N-port numerical reference, worker/schema execution and native desktop import/run/export, invalidation/recovery and wide/narrow inspection | Calibrated fixtures, uncertainty and physical qualification remain distinct gates |
| Calibration and uncertainty | Supplied fixture models only | Versioned calibration standards/method, calibrated multiport data, covariance/noise propagation and independently measured DUT comparison with predeclared uncertainty/tolerances |
| Passive causal broadband fitting | SI08-S04 supplied stable real-pole fit | Automatic stable complex-conjugate pole selection, independently assessed/enforced broadband passivity, retained pre/post models, DC/high-frequency behavior, held-out frequencies and intersample violation witnesses |
| Transient circuit use | Existing bounded rational/transient references | Automatic fitted models in loaded circuits, analytical/circuit references, refinement, long-horizon stability and energy/passivity checks |
| Full-family acceptance | No qualified family benchmark | Frozen versioned manifest mapping every original target/open gap to executed source-bound evidence; physical/measurement validity and independent numerical review; no open target gaps |

Work order is multiport fixture algebra, calibration/uncertainty foundations,
causality/DC policy qualification, general passive fitting, then integrated
transient and measured acceptance. Existing mathematical kernels may be reused
only inside their verified scope. Do not relabel supplied two-port algebra as
calibration, sampled passivity as broadband passivity, or a causal fitted model
as evidence that the source data are causal.

Before each remaining numerical implementation, freeze an observable-specific
reference, units, validity domain and tolerances. Measurement tolerances depend
on reviewed fixture/standard uncertainty and cannot be invented from synthetic
test errors. No fabricated or downloaded unlicensed measurement corpus is used.
The full-family benchmark remains definition-pending until these choices and
data are actually pinned. Release qualification and required human numerical
review remain separate from development milestones.

The authoritative status remains in
[the capability backlog](parity-capability-backlog-v1.json). SI08 remains
`in_progress`; no family is closed merely because its listed stages passed.

The original [offline multiport receipt](validation/parity/SI08-multiport-20261024.json)
remains historical evidence of that source snapshot. The later
[integration record](validation/SI08_MULTIPORT_INTEGRATION_20261024.md) covers
13 numerical/worker/workflow checks and actual headless panel handlers, with
native interactive acceptance completed and source-bound. Replay current bounded
integration evidence with `python -B scripts/verify_multiport_integration.py
--output FRESH.json --log FRESH.log`. Numerical recovery tolerances remain
fixture-specific 2e-12 absolute and relative. SI08-S05 is done; full SI08 remains in progress.
The native software-stage receipt is
[SI08-S05 native evidence](validation/parity/SI08-S05-native-20261024.json);
its validator is `scripts/parity_multiport_native_gate.py`.
