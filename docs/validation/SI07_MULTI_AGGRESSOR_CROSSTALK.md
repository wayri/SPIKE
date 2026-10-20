<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI07-S08 verification: sampled multi-aggressor crosstalk

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Verified 18 October 2026. **Done for the bounded stage; experimental,
production-unqualified.** SI07 and complete PI/SI parity remain open.
The [method ledger](../MULTI_AGGRESSOR_CROSSTALK.md) retains reviewed primary
references, original derivation, units, conditioning and multiphysics limits.

## Executed evidence

The [canonical source-bound receipt](parity/SI07-S08.json) retains **9 tests,
zero skips**, and the actual execution log (unbundled local record: `parity/SI07-S08-schema-verified.log`).
Six numerical and three actual worker/schema/example tests executed. Reproduce
into new repository paths:

```powershell
.venv/Scripts/python.exe scripts/parity_pisi_gate.py --stage SI07-S08 --output build/aggressor-check.json --log build/aggressor-check.log
```

Checks include:

- Independent coupled four-port physical KCL/KVL equations, with series L and
  shunt C, biased PWL sources and exhaustive enumeration of all four signed
  waveform patterns. A genuine nonzero common-inductor fitted-memory case
  includes common initial response and two fixed drivers.
- Analytic two-mode scalar RLC transfer for one aggressor, independently
  checking the victim contribution and upper/lower envelopes.
- Baseline-only common fitted/L/C state and fixed drivers, zero-state basis
  contributions, original source/request immutability and reconstructable
  baseline/basis/pattern digests. Five actual fitting calls for two aggressors.
- Both selected extreme fixed-pattern full traces independently checked; an
  intentionally corrupted witness rejects the whole operation.
- Reversed request ordering, source-ordered results, zero-deviation tie signs,
  earliest sampled ties and observations that omit the source-horizon endpoint.
- Reference impedances 1/25/100/1,000 ohms, simultaneous time/L/C scaling by
  0.001, and checks against the unchanged physical voltage trajectory.
- Unknown/duplicate/victim/Boolean/nonfinite/malformed sources and initial-state
  identity rejection, mirrored arithmetic overflow, aggregate pre-fit work and
  result budgets, and cancellation across actual execution.
- Actual top-level worker, strict registered public schemas, canonical original
  input identity and an executable original three-port conductance/RLC example
  independently enumerated through physical equations.

Preset physical-reference and direct-witness voltage acceptance is 2e-10 V
absolute plus 1e-9 relative. The retained envelope/reference/time-scaling probe
measured maximum discrepancy 5.2735593669694936e-15 V. Its nonzero-memory fixture
measured direct-superposition residual 3.920475055707584e-16 V, five actual
solutions, estimated work 539640 and eight requested samples. Reproduce with
`build/probe_multi_aggressor.py`; output `build/si07-s08-reference-errors.json`.
These are mathematical reference errors, not physical measurement uncertainty
or a bound between requested samples.

All **19 earlier PI/SI numerical stages** were actually rerun after shared
worker/runner changes. Canonical receipts retain executed
`*-aggressor-reverified.log`; preceding receipts are preserved as
`*-pre-aggressor.json`. No source hash was refreshed without executing tests.
The first broader run found missing draft declarations in the two new schemas.
After adding the required 2020-12 metadata, 16 schema/contract checks passed,
and the nine-test affected stage was actually rerun; its preceding receipt is
retained as `SI07-S08-pre-schema.json`.

Broader focused regressions passed **292 tests**, zero skips/failures/errors,
in 34.265 seconds. Log: `build/si07-s08-focused.log`; scope includes
retained PI/SI, mechanical/thermal, network graphs, schemas and tracking guards.
The initial schema failure log remains `build/si07-s08-focused-initial.log`.
Ten final documentation checks and 50 final completion-tracking/schema checks
passed after roadmap updates. The architecture guard passed earlier in this
turn, but its final run is **blocked by an unrelated desktop workspace change**:
`app/src/workspaceViewWindows.ts` imports native IPC outside the guard's approved
bridge list. This stage did not change that file or weaken the guard. The actual
failure is retained in `build/si07-s08-architecture.log`; repository-wide
architecture health is not claimed. PI/SI numerical stage receipts remain valid. A concurrent `service.py` change
also made the previous structural receipt stale after the initial successful
tracking run. The 16 structural stage tests were actually rerun with zero skips
before updating its canonical receipt; the earlier receipt is archived as
`GP07-S01-pre-aggressor-shared-worker.json` and the new execution is retained in
`GP07-S01-aggressor-shared-worker.log`. Completion-tracking checks were then rerun.
The full release suite was not rerun; earlier full-Python provider connection failures remain
[unresolved](SI07_CAPACITIVE_NETWORK_TRANSIENT.md). No clean release claim is made.

## Independent review and multiphysics limits

Independent read-only review found no actionable correctness issue and ran
**31 tests, zero skips**: six new numerical, three new worker/schema/example,
eight initialized numerical, three initialized contract, eight energy numerical
and three energy contract checks. It traced common-state/fixed-driver ownership,
bias reflection, source order, compensated sums, sampled sign envelopes,
earliest ties, N+3 actual witness solves/digests, resource and cancellation
admission. Human knowledgeable numerical review before release remains required.

The envelopes are exact for the supplied finite fixed-polarity waveform family
at requested samples up to floating arithmetic. Each sample can require a
different pattern; only the global sampled upper/lower witnesses are directly
executed. A large common mode can mask very small contributions within the
absolute witness tolerance. No intersample peak, skew/data-sequence search,
eye/jitter/BER, nonlinear IBIS/AMI or measured/vendor correlation is established.

Port/source/state provenance and the actual baseline retain future coupling
identity. Quadratic resistor heat, signed work and stored energy include cross
terms and must not be summed from basis results. Construct a full selected
pattern and run the continuous energy ledger for its work/heat/storage.
This stage performs no thermal deposition, material feedback, field, mechanical
or general multiphysics solve and does not close the parent SI07 capability.
