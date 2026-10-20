<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S03 verification: supplied uniform sampled RLGC line networks

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Verified 18 October 2026. **Done for this bounded stage; experimental,
production-unqualified.** SI02 and full PI/SI parity remain open.
The [method ledger](../RLGC_LINE_NETWORK.md) retains primary references,
independent derivation, SI units, conditioning and physical/coupling limits.
Reviewed: Staelin, *Electromagnetics and Applications* (2011), chapter 8,
section 8.3.1, equations (8.3.3)-(8.3.12), printed pages 249-250
([official MIT text](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf)).
The text explicitly limits pure-TEM applicability with conductor resistance.
No external code, fixtures, figures or prose were imported.

## Executed evidence

The [canonical source-bound receipt](parity/SI02-S03.json) retains **18 tests,
zero skips**: fifteen numerical and three actual worker/schema/example/handoff
checks. Its actual log (unbundled local record: `parity/SI02-S03-rlgc-line-reverified.log`) records names.
Reproduce into fresh repository paths:

```powershell
.venv/Scripts/python.exe scripts/parity_pisi_gate.py --stage SI02-S03 --output build/rlgc-check.json --log build/rlgc-check.log
```

- Independent spatial matrix exponentials plus terminal wave boundary solves
  check complex two-port entries across DC through 1.1 GHz, unequal independent
  per-frequency R/G and non-characteristic port reference. The oracle uses
  neither the kernel's scaled scattering formula nor its propagation root.
- A symmetric series-half/shunt/series-half lumped ladder converges at second
  order toward the continuous uniform line, checking the governing circuit
  interpretation using finite sections and independent boundary solves.
- Analytic exactly-real DC thru, series-resistance and shunt-conductance limits,
  matched lossless delay/power and Heaviside attenuation/delay are checked.
- Equal-reference port reversal, reciprocity, sampled passivity and physical
  length/per-unit scaling are checked. The short-line case retains first-order
  reflection; the highly attenuating line retains tiny finite transmission.
- A matched line with phase 9e5 radians and attenuation 2e-10 nepers checks the
  positive-sum propagation-root calculation against independently known
  Heaviside attenuation. It avoids subtractive erasure of weak loss.
- Strict malformed/Boolean/nonfinite/negative/unknown/tuple/type cases,
  binary64 frequency collapse, sample bounds, arithmetic/propagation limits,
  invariant failures, immutable snapshot under callback mutation and
  cancellation reject without a successful partial network or numerical repair.
- Actual worker output validates against strict registered 2020-12 schemas and
  a second independent physical V/I spatial solve. Original request/digest and
  terminal names are checked. The executable original 5-m example is tested;
  its network enters the actual existing resampling worker, preserving samples.

Preset numerical spatial-oracle tolerance is 2e-13 absolute plus 2e-13 relative
per S entry; the independent worker oracle uses 2e-12 plus 1e-10 relative.
Matched delay and power tolerances are 1e-14 absolute, Heaviside 5e-15;
weak-loss amplitude tolerance is 2e-15. The ladder's finest-grid error must be
below 1.5e-5, with every refinement ratio between 3.9 and 4.1. These are
dimensionless S errors, not physical measurement uncertainty.

The retained `build/probe_rlgc_line.py` produces
`build/si02-s03-reference-errors.json`. Maximum spatial-reference error was
7.850462293418876e-16. Ladder errors at 16/32/64/128/256 sections were
1.1189029974562064e-3, 2.795445677816779e-4, 6.987482494901794e-5,
1.7467999032663864e-5 and 4.366955560506724e-6; ratios were 4.00259,
4.00065, 4.00016 and 4.00004. At 300 nepers, transmission amplitude was
5.148200222412013e-131 with zero measured relative discrepancy from exp(-300)
in this binary64 check. The weak-loss amplitude discrepancy was zero against
exp(-2e-10) in its test. No claim of exact arithmetic or measured accuracy follows.

All **24 earlier PI/SI numerical stages** were actually rerun after shared
worker/runner integration. Canonical receipts point to
`*-rlgc-line-reverified.log`; prior receipts remain archived as
`*-pre-rlgc-line.json`. No hash-only refresh replaced actual execution.
Broader PI/SI, structural/thermal, network, schema and evidence regressions
passed **352 tests**, zero skips/failures/errors (`build/si02-s03-focused.log`).
Architecture passed (`build/si02-s03-architecture.log`). Ten documentation
checks and 55 final completion-tracking/schema checks passed after Done updates.
Actual logs/counts are recorded in backlog verification metadata.

The initial final-tracking run exposed six historical v1 import-stage receipts
against the current v2 import-evidence contract. Six pinned CLI imports were
actually replayed and their complete v2 receipts validated. Prior receipts
remain as `*-pre-rlgc-line-v2.json`; the replay log is
`build/si02-s03-import-reexecution.log` and the initial failed tracking log is
`build/si02-s03-tracking-initial-failed.log`. Tracking and broader regressions
were rerun against the refreshed evidence; no hash-only upgrade was used.

Independent read-only numerical review found no remaining actionable defect
and separately ran **18 tests, zero skips**. Scope and limitations are retained
in `build/si02-s03-independent-review.json` and backlog verification metadata.
Knowledgeable human numerical review before release remains required. Full
release tests were not rerun; prior provider connection failures remain
[unresolved](SI07_CAPACITIVE_NETWORK_TRANSIENT.md). No clean release qualification
is claimed.

## Physical and multiphysics limits

The model is a supplied uniform scalar distributed circuit with constant
positive L/C and independent nonnegative R/G at explicit frequencies. Equal
real reference and left/right terminal orientation are fixed. Sampled
passivity/reciprocity do not establish causal broadband material laws or
transient validity. No interpolation or fitting is executed by this solver.

Original constitutive tables preserve identity for future material/geometry
work. No excited fields or heat are calculated from the unexcited S network;
temperature feedback, loss ownership/volumetric deposition and conservative
thermal transfer remain separate. General complex constitutive dispersion,
coupled conductors/branches/discontinuities/returns, geometry and skin/proximity
extraction, physical validation and production qualification remain open.
