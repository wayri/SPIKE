<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI07-S07 verification: continuous RLC energy ledger

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Verified 18 October 2026. **Done for the bounded stage; experimental,
production-unqualified.** SI07 and complete PI/SI parity remain open.
The [method record](../RLC_ENERGY_LEDGER.md) retains the independent derivation,
reviewed primary sources, continuous integration, ownership and limitations.

## Executed evidence

The [canonical source-bound receipt](parity/SI07-S07.json) retains **11 tests,
zero skips**, and the actual execution log (unbundled local record: `parity/SI07-S07-energy-reverified.log`).
Eight numerical and three actual worker/schema/example tests executed. Reproduce
into new repository paths:

```powershell
.venv/Scripts/python.exe scripts/parity_pisi_gate.py --stage SI07-S07 --output build/energy-check.json --log build/energy-check.log
```

Checks include:

- Analytic loaded-RLC free/forced damping references integrated independently
  with scalar quadrature for source/network work, resistor heat and endpoint
  storage. Initial energy is included for charged/energized cases.
- Genuine nonzero fitted-memory physical reference, distinguishing network
  heat from its known internal inductor storage change without assigning generic
  physical energy to fitted states.
- Coupled multiport PWL physical-equation quadrature, per-port identities,
  refinement invariance and ledger additivity across a true nonzero-ramp split
  at 0.47 s, absent from the original observation grid.
- A single 1,000-second interval requiring at least 15 covariance doublings;
  independently split scalar quadrature resolves its short initial transient.
- Mixed RL-only, RC-only and pure-R boundaries with reversed request order,
  finite/zero pure resistance, independent scalar energy references, reference
  impedances 1/25/100/1,000 ohms, and simultaneous time/L/C scaling by 0.001.
- Signed source work, stable-active signed network work and exactly zero heat
  for a zero-resistance boundary. No clipping or balance redistribution occurs.
- One actual fit/trajectory, exact unchanged v1/v2 public output, isolated private
  observer copies, aggregate work/byte/precision admission and cancellation.
- Actual worker, strict registered schemas, immutable input identity, retained
  initial-state/source provenance and an executable original free-decay example.

Preselected numerical acceptance is 1e-10 J absolute plus 1e-9 relative for each
independent energy comparison. The retained default analytic loaded-RLC probe
measured source-work error 6.245004513516506e-17 J, network-work error
6.938893903907228e-18 J and resistor-heat error 6.938893903907228e-18 J.
Its maximum absolute balance residual was 6.938893903907228e-17 J, Gramian
identity relative residual 1.4500831120318485e-16 and symmetry relative residual
2.0274980238578004e-16, with seven actual doubling steps. Probe:
`build/si07-s07-energy-errors.json`. These are mathematical reference errors,
not physical measurement uncertainty or a global integration-error certificate.

All **18 earlier PI/SI numerical stages** were actually rerun after the shared
worker/runner changes and private interval instrumentation. Canonical receipts
retain executed `*-energy-reverified.log`; preceding receipts are preserved as
`*-pre-energy.json`. No source hash was refreshed without executing the tests.

Broader focused regressions passed **282 tests**, zero skips/failures/errors,
in 36.954 seconds. Log: `build/si07-s07-focused.log`; scope includes retained
PI/SI, mechanical/thermal, network graphs, schemas and evidence/tracking guards.
Architecture and ten final documentation checks passed, together with 49 final
tracking/schema checks after roadmap/backlog completion updates. The full release
suite was not rerun; earlier full-Python provider connection failures remain
[unresolved](SI07_CAPACITIVE_NETWORK_TRANSIENT.md). No clean release claim is made.

## Review and remaining limits

Independent read-only review found no actionable correctness issue. It ran 32
ledger plus existing RLC numerical/contract tests with zero skips and confirmed
the Gramian orientation/doubling, physical h factor, mixed current/source rows,
signed energy, unit/reference scaling, precision/resource admission and reuse.

The ledger integrates supplied boundary resistor heat and L/C storage. Signed
work entering the fitted network is not automatically heat; generic internal
storage is unspecified. Interval joules retain port/source identity for a later
thermal ownership and deposition contract, without executing thermal transfer.
Temperature feedback, managed sessions, parameter-change work, arbitrary
nonlinear/DAE models, measured validation and robust nonnormal-stability
qualification remain open. Knowledgeable human numerical review before release
remains required.
