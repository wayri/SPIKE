<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S05 verification: supplied piecewise RLGC cascade

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Verified 18 October 2026. **Done for this bounded stage; experimental,
production-unqualified.** SI02 and full PI/SI parity remain incomplete.
The [method ledger](../RLGC_LINE_CASCADE.md) retains independent derivation,
SI/RMS conventions, conditioning, ownership and exact physical limits.
Reviewed primary source: Staelin, *Electromagnetics and Applications* (2011),
section 8.1.2, equations (8.1.14)-(8.1.16) and interface discussion, printed
pages 232-234; section 8.3.1, equations (8.3.3)-(8.3.12)/(8.3.16), printed
pages 249-251 ([official MIT text](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf)).
No external implementation, data, figures or prose were copied.

## Executed evidence

The [canonical source-bound receipt](parity/SI02-S05.json) retains **14 tests,
zero skips**: eleven numerical and three actual worker/schema/example/CLI
checks. Its actual log (unbundled local record: `parity/SI02-S05-rlgc-cascade-reverified.log`) records names.
Reproduce into fresh repository paths:

```powershell
.venv/Scripts/python.exe scripts/parity_pisi_gate.py --stage SI02-S05 --output build/cascade-check.json --log build/cascade-check.log
```

- Independent physical spatial matrix exponentials chained across two/three
  different sections, with direct terminal boundary solves, verify external
  complex S and coherent section V/I. The oracle uses no leaf S, connection
  matrix or production overlap formula.
- Separate section quadrature checks conductor/dielectric heat and global
  input. Local incident waves reconstructed from physical boundary V/I match
  the actual derived child requests. Ideal junction V, opposing inward currents
  and signed power cancellation are checked; corrupt child junction/loss outputs
  reject instead of being repaired.
- Splitting one uniform line into identical sections preserves external S,
  matching interior fields and summed heat. One section retains exact parent
  network/field identity. Added segmentation is not a new physical discontinuity.
- An independent lossless quarter-wave 50/100-ohm impedance step has exact
  S=[[-0.6,-0.8],[-0.8,0.6]] at the common real reference. This checks reflection
  magnitude, transmission phase, reciprocity and end orientation.
- Coherent two-end excitation, physical reversal and amplitude/unit scaling,
  lossless and exact-zero cases, original request/digest and immutable inputs,
  mismatched references/grids, malformed/Boolean/duplicate/out-of-range controls,
  numerical/conditioning/underflow failures and cancellation are covered.
  Work/nested-output preflight is tested before any numerical parent call.
- Actual worker output and CLI result both validate against registered strict
  2020-12 schemas. The independently authored saved three-section example runs
  as Python and through `rlgc-cascade request.json`; its complete fields and
  loss ledger are compared with a second independent spatial/quadrature oracle.

Preset independent S tolerance is 2e-13 absolute plus 2e-13 relative; field
tolerances are 3e-12 V/3e-14 A absolute plus 1e-12 relative. Quadrature heat
comparisons use 2e-12 W per section and 3e-12 W global. Interface test thresholds
are 1e-12 V, 1e-13 A and 1e-12 W. The separate worker oracle uses 2e-12 S plus
1e-10 relative, 3e-11 SI V/I plus 1e-10 relative and 2e-12 W plus 1e-10 relative
for heat. Production connection conditioning <=1e8, scaled solve <=1e-10,
interface V/I <=1e-9 relative and power <=1e-10 relative remain unchanged;
zero-scale identities must be exact. Raw residuals remain unmodified.

`build/probe_rlgc_cascade.py` produces `build/si02-s05-reference-errors.json`.
Six network comparisons, 60 probes and 15 section quadratures measured maximum
S error 1.2123818431320796e-15, voltage error 1.0031404150080652e-14 V and
current error 1.8253379971363983e-16 A. Conductor/dielectric integral errors were
9.71445146547012e-17 W and 4.163336342344337e-17 W. Maximum global power residual
was 1.0824674490095276e-15 W; maximum junction power residual was
9.992007221626409e-16 W. These are ideal-model mathematical errors, not physical
measurement uncertainty or a claim of exact arithmetic.

All **26 earlier PI/SI numerical stages** were actually rerun after shared
worker/runner integration. Canonical receipts point to
`*-rlgc-cascade-reverified.log`; earlier receipts remain archived as
`*-pre-rlgc-cascade.json`. No hash-only refresh replaced execution.
Broader PI/SI, CLI, structural/thermal, network, package, schema and evidence
regressions passed **483 tests**, zero skips/failures/errors
(`build/si02-s05-focused.log`). Architecture passed
(`build/si02-s05-architecture.log`); SI frontend component/mapping tests passed
(`build/si02-s05-si-ui.log`). Eleven final documentation checks and 57
completion-tracking/schema checks passed after Done updates. Actual logs/counts
are recorded in backlog verification metadata.

Nine real CLI SI/PI readiness cases passed before progression
(`build/pisi-stability-20261018-next/readiness.json`) and after integration
(`build/pisi-stability-20261018-cascade/readiness.json`), including explicit
RC/RLC load studies, unchanged RLC timestep acceptance, coupled SI waveform/eye,
10G numerical reference, Touchstone export/reinspection and native routed-copper
DC/AC/transient. These are [bounded workflow checks](../RUN_SI_PI_NOW.md), not
board-specific or installed native-visual validation.

Independent read-only numerical review found no actionable defect and separately
ran **14 tests, zero skips**. Scope/limits remain in
`build/si02-s05-independent-review.json` and backlog verification metadata.
Knowledgeable human numerical review before release remains required. Full
release tests were not rerun; prior provider connection failures remain
[unresolved](SI07_CAPACITIVE_NETWORK_TRANSIENT.md). No clean release qualification
is claimed.

## Physical and multiphysics limits

The model is an ordered scalar series cascade of supplied uniform RLGC sections
with ideal equal-reference junctions and independent positive-frequency RMS
cases. It does not model a physical bend/launch/via discontinuity, three-way
branch, return change, coupled conductors or inferred material/geometry law.
Nonnegative sampled R/G and a power ledger do not establish broadband causality,
dispersive-material energy or real-board applicability.

Section IDs, original constitutive/probe requests and actual derived local
drives retain cross-domain identity. Conductor-loop/dielectric heat is counted
once per section. Internal signed transport cancels; it is not a thermal
source. Individual conductor heat split, volumetric ownership, conservative
thermal mapping and temperature feedback remain separate, as do DC/transient
fields, measured correlation and production qualification.
