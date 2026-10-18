<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S06 verification: supplied ideal RLGC star junction

Verified 19 October 2026. **Done for the bounded stage; experimental,
production-unqualified.** SI02 and full PI/SI parity remain incomplete.
See the [method ledger](../RLGC_LINE_JUNCTION.md) for the reviewed Staelin
chapter 8 sections, original wave/node derivation, RMS/SI conventions,
conditioning, source identity, resource bounds and physical omissions.
No external implementation or example data was copied.

## Executed acceptance

The [canonical source-bound receipt](parity/SI02-S06.json) and its
[actual test log](parity/SI02-S06-star-junction-20261019.log) record **15 tests,
zero skips**: twelve numerical and three actual worker/CLI/schema/example
checks. Reproduce to fresh paths:

```powershell
.venv/Scripts/python.exe scripts/parity_pisi_gate.py --stage SI02-S06 --output build/my-star-check.json --log build/my-star-check.log
```

The independent oracle solves physical left V/I states using spatial matrix
exponentials, external V+rI boundary conditions, common right voltage and
summed right current. It uses neither production S matrices nor the junction
wave connection. Independent quadrature verifies each leg's conductor and
dielectric heat. Matched three-port phase/one-ninth versus four-ninths power,
eight-port unitarity, reversed-orientation two-leg cascade equivalence,
coherent scaling/port permutation, exact zero and probe independence are
checked. Trapezoidal heat integration has approximately fourfold error reduction
on 16/32/64 cells. Binary-exact matched, 40-neper legs retain scattering near
exp(-80) and agree with independent analytic heat, without a growing transfer
matrix in production.

Preset physical-oracle tolerances are 2e-12 absolute plus 1e-10 relative;
strong attenuation uses 1e-47 absolute plus 2e-12 relative. The implementation
retains condition <=1e8, solve <=1e-10 relative, common-node voltage/KCL
<=1e-9 relative and power <=1e-10 relative. Exact-zero identities remain exact.
Malformed/cross-field/schema rejection, conditioning/nonfinite/underflow,
combined resource limits before child solves, cancellation and corrupted child
boundary/ledger/provenance rejection are exercised. No clipping, passivity
projection or conservation-residual redistribution is used.

`build/rlgc-line-junction-metrics.json` retains three independent network
comparisons, 27 probes and nine conductor/dielectric integral pairs. Maximum
absolute errors were 6.2373e-16 in S, 5.0243e-15 V, 1.5701e-16 A,
1.2143e-17 W conductor heat and 2.1684e-18 W dielectric heat. Trapezoid errors
were 1.220024e-6, 3.046293e-7 and 7.613385e-8 W. Maximum global power residual
was 6.2797e-16 W; node voltage/current/power residuals were 3.3821e-15 V,
1.1857e-16 A and 1.2212e-15 W. These are mathematical fixture errors, not
measurement uncertainty.

All **27 earlier PI/SI numerical stages were actually rerun** against the
shared integration. Their canonical receipts point to
`*-star-junction-20261019-reverified.log`; original receipts are retained as
`*-pre-star-junction-20261019.json`. No hash-only refresh replaced execution.
Independent review separately ran all 15 tests with zero skips and found no
actionable issue (`build/si02-s06-independent-review.json`).

Broader CLI, SI workflow/channel/network-graph and schema regressions passed
**99 tests, zero failures/errors/skips**
(`build/si02-s06-focused-workspace-temp.log`). The first focused attempt failed
because the sandbox's default temporary directory denied access; its log is
preserved at `build/si02-s06-focused.log`. The unchanged tests passed using a
repository-local TEMP/TMP directory. No test or tolerance was disabled.

All nine actual SI/PI CLI readiness cases passed before this integration
(`build/pisi-readiness-20261019-post-hold/readiness.json`) and after it
(`build/pisi-readiness-20261019-star-junction/readiness.json`). Native copper
DC/AC/transient, supplied RC/RLC time refinement, coupled/10G reference SI,
waveform/eye/TDR and exported Touchstone reinspection remain bounded examples.
Architecture passed. Documentation/reference and tracking checks are recorded
in the backlog verification metadata.

## Actual-board audit and qualification boundary

[Current EBrake1 and Marble checks](BOARD_PISI_READINESS_20261019.md) retain
complete imported boards and actual CLI admission, with explicit diagnostic
loads. They establish neither full-board SI/PI nor measured signoff.
Marble's former C383 isolation expectation was wrong after corrected backside
import. Raw source and independent native KiCad geometry prove that pad is
connected; the version-2 audit retains the unchanged resistance/conservation
gates and separate manufactured disconnected controls. Current Marble RT0 DC
refinement passes at 0.5/0.25/0.125 mm. EBrake refinement and wider AC/SI material,
reference and geometry coverage remain open; the supplied star does not bypass
those gates.

Before this integration, a separate guarded local full run passed 4,293 tests
with zero failures/errors and 69 skips. A fresh integration full Python run is
retained under `build/si02-s06-full-python/`; its result must be read with the
before/after source guard and explicit skips. Ongoing optional-runtime
qualification in the other engineering chat is separate. Neither the earlier
full run nor this bounded stage is a release qualification.

Each supplied leg retains its complete coherent fields, separately owned
conductor/dielectric heat and original material/line assumptions. The common
ideal node adds no heat or storage. Arbitrary graphs, coupled conductors,
physical junction/return parasitics, geometry extraction, causal material
models, DC/transient fields, thermal mapping/feedback, measured validation and
knowledgeable human numerical release review remain open.
