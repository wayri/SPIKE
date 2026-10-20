<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI07-S09 verification: supplied crosstalk timing corners

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Verified 18 October 2026. **Done for the bounded stage; experimental,
production-unqualified.** SI07 and complete PI/SI parity remain open.
The [method ledger](../CROSSTALK_TIMING_CORNERS.md) retains reviewed primary
references, independently derived translation/clipping and initial-state
semantics, units, conditioning, work limits and multiphysics ownership.

## Executed evidence

The [canonical source-bound receipt](parity/SI07-S09.json) retains **9 tests,
zero skips**, and its actual execution log (unbundled local record: `parity/SI07-S09-timing-reverified.log`).
Six numerical and three actual worker/schema/example tests executed. Reproduce
into new repository paths:

```powershell
.venv/Scripts/python.exe scripts/parity_pisi_gate.py --stage SI07-S09 --output build/timing-check.json --log build/timing-check.log
```

Checks include:

- Hand-derived positive/negative shifted knots, clipped endpoint interpolation,
  endpoint holds at exact/beyond-horizon delays, and byte-identical zero-delay
  source representation. Independent dense evaluation checks the PWL functions.
- Three timing corners and all four fixed-polarity combinations through
  independent physical KCL/KVL conductance/RLC equations with a genuine
  common-inductor fitted-memory state. Common initial response and two fixed
  drivers are retained exactly once per corner.
- Complete actual child results, source-ordered delay maps, unchanged fit,
  initial state, horizon and observations; samplewise finite-family extrema,
  attaining corner ids, raw margins and directly checked global witness traces.
- Fifteen actual fitting calls for three corners/two aggressors, correct summed
  shifted-grid work, unchanged original request/digest and exact nominal parent
  identity. Equal-corner ties prefer declared order and parent tie rules.
- Reference impedances 1/25/1,000 ohms and simultaneous delay/time/L/C scaling
  by 0.001 preserve physical voltages and scaled witness times.
- Observation-grid refinement preserves shared samples and can only expand
  observed extrema within tolerance; adding supplied corners can only expand
  the finite-family voltage envelope.
- Malformed/duplicate/empty/oversized ids and maps, Boolean/nonfinite delays,
  absorbed subnormal delays, collided interior knots and unsupported source
  identity fail closed. An invalid final corner and all-corner work/byte limits
  reject before any fit; cancellation is checked before/between/after execution.
- Actual top-level worker, strict registered 2020-12 schemas, original source
  immutability and executable nominal/late-clock/early-data example. Hand-built
  shifted source tables are separately enumerated through physical equations.

Preset physical-reference voltage acceptance is 2e-10 V absolute plus 1e-9
relative. The retained finite-family/reference/time-scaling probe measured
maximum discrepancy 4.773959005888173e-15 V and maximum parent direct-witness
residual 5.551115123125783e-16 V. The nonzero-memory example used 15 actual
solutions, estimated work 1723320, three corners and eight observations.
Reproduce with `build/probe_crosstalk_timing.py`; retained output is
`build/si07-s09-reference-errors.json`. These are mathematical verification
errors, not physical measurement uncertainty or continuous timing-error bounds.

All **20 earlier PI/SI numerical stages** were actually rerun after shared
worker/runner integration. Canonical receipts retain `*-timing-reverified.log`;
prior receipts remain archived as `*-pre-timing.json`. No source hash was updated
without executing tests. Broader focused regressions passed **302 tests**, zero
skips/failures/errors, in 42.234 seconds. Log:
`build/si07-s09-focused.log`; scope includes retained PI/SI, structural/thermal,
network graphs, public schemas and source/evidence tracking guards.

Independent read-only review found no actionable issue and independently ran
**29 tests, zero skips**: six timing numerical, three timing contract, six parent
multi-aggressor numerical, three parent contract, eight initialized numerical
and three initialized contract checks. It traced signed translation, endpoints,
representability, common state, corner/witness ties, complete nested budgets,
all-corner pre-fit admission and cancellation.

The final architecture guard passed (`build/si07-s09-architecture.log`). Its
earlier unrelated invalid-UTF8 `app/src/App.tsx` failure cleared through other
workspace work; this stage did not alter that file or weaken the guard.
Ten final documentation checks and 51 final completion-tracking/schema checks
passed after Done updates. Actual logs and counts are retained in backlog
verification metadata. The full release suite was not rerun;
earlier provider connection failures remain
[unresolved](SI07_CAPACITIVE_NETWORK_TRANSIENT.md). No clean release claim is made.

## Scope and multiphysics limits

The envelope covers only the supplied finite delays, fixed waveform polarities
and requested observation times. Endpoint holds and unchanged supplied local-zero
state define each initial-value experiment; negative-time source history and
settling are not inferred. Finer observation or corner sets can reveal worse
values. Continuous skew, probabilistic jitter/BER, intersample peaks, nonlinear
drivers and physical/VNA/TDR correlation remain open.

Complete corner/source/state provenance allows a later coupled study to select
a reproducible full pattern. Heat/work/storage are quadratic and must not be
summed across basis responses or corners. A full selected initialized request
can be passed to the continuous energy ledger; no thermal deposition, material
feedback, field or mechanical execution occurs here. Human knowledgeable
numerical review before release remains required. This bounded Done stage does
not close the SI07 capability or complete PI/SI parity.
