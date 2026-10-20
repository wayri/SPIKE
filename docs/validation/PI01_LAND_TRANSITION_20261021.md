<!-- SPDX-License-Identifier: Apache-2.0 -->
# PI01-S02 land fields and explicit contact patches — 21 October 2026

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

**Verified bounded increment; PI01-S02 remains in progress.** A supplied 3-D
rectangular land now supports finite current patches on all six exterior sides,
separate face potentials, conservative three-component fields and integrated
Joule heat. Semantic attachment labels do not collapse different patch areas
or impose equal voltage. This is an experimental in-process reference and
runnable example, not automatic annular/board mapping or a new desktop engine.

The [method](../DC_LAND_TRANSITION.md) records primary sources actually reviewed,
the independently authored hexahedral RT0 derivation, exact local mass, weak
law, full gauge equation and declared acceptance. [ADR0126](../adr/0126-conservative-land-transition-face-patches.md)
records ownership, interfaces and limits. No external implementation, mesh,
dataset or new dependency was introduced; existing DC and CFD kernels were
not edited.

## Executed numerical evidence

- [Current partial receipt](parity/PI01-S02-land-transition-20261021.json),
  raw log ([bundled original execution log](parity/PI01-S02-land-transition-20261021.log)), and
  [retained fields/refinement report](parity/PI01-S02-land-fields-20261021.json):
  **23 tests, zero skips**, with 36 source files hashed before/after/current.
  These are 14 new main/oracle tests and nine prior axial/integration tests
  actually reexecuted. The gate also produces fresh example and three-level
  continuum-comparison field records; it enforces `stage_complete=false` and
  `production_qualified=false`. Prior partial receipts remain historical.
- The unchanged, strengthened PI01-S02A receipt is independently revalidated by
  this gate. No source hashes or historical receipt results were patched.
- Actual example CLI, saved-result witness validation and overwrite rejection
  execute in the suite. Corrupted mapping, vector components, constitutive
  potentials, gauge, volume, heat and completion claims reject.
- **47 unchanged DC/Marble regressions passed**, zero skips, in a separate
  focused invocation: copper-domain, density, conforming DC, iterative RT0,
  Marble probe and refinement-audit modules. Together with the 23 source-bound
  cases, these are 70 distinct numerical tests in two invocations.
- **17 tracking/evidence checks passed**, zero skips; current Done-stage source
  envelopes, partial-stage non-completion and corrupted land subreports are
  checked. Architecture and scoped whitespace checks pass. The reference
  inventory is regenerated and checked separately; this is not a full-suite run.

Independent Astra review verified signs, local mass, gauge-inclusive conservation,
terminal work and a separately derived cosine-series continuum oracle. It also
implemented independent Gauss integration and all-three-component harmonic-field
tests. Two P2 counterexamples were repaired and rechecked: intermediate current
stamp underflow, and validator norm overflow accepting a forged interior trace.
All 14 focused tests and original/extended counterexamples passed on re-review;
no blocking findings remain for this bounded method. Knowledgeable human release
review remains pending.

Runtime: Python 3.11, NumPy 2.2.6 and SciPy 1.17.1. Sparse factorization fill/time
is supervised offline; the scaled spectral screen is not a formal error bound.

## Independent continuum and physical results

On a 1x1x0.2 mm prism, +1 A enters the left half of the z-min face and -1 A
leaves its right half. Both deliberately share an attachment label while
retaining distinct finite supports and mean potentials. The independently
derived series gives R=3.29055463660345e-5 ohm at 4096 terms, with positive
omitted tail <=5.3031e-13 ohm (ordinary floating evaluation, not interval proof).

| Grid | Resistance relative error |
| --- | ---: |
| 4x1x2 | 0.733684% |
| 8x1x4 | 0.313202% |
| 16x1x8 | 0.112677% |

The finest passes the original <2% criterion and improves over coarse. The
test compares both endpoints of the independent series-tail interval. Separate
checks recover exact uniform fields on all coordinate axes and all three
varying components of a harmonic quadratic potential on nonuniform cells.
Independent SI Gauss integration of the returned fields reproduces face current,
physical volume and each cell/total Joule loss, rather than comparing only an
implementation-shaped matrix statistic.

The retained three-patch example solves 32 cells, 2e-10 m3, with total heat
8.329781328558349e-5 W and terminal work 8.32978132855792e-5 W. Maximum recovered
face/boundary/gauge error is 6.23e-14 A; the scaled condition estimate is about
2218. Heat remains W (mean density W/m3), separate from energy J. Cell identities
and complete reconstructed component endpoints support later explicit thermal
transfer; no thermal association or material feedback is inferred.

Face-area fractions are computed before multiplying by patch current, retaining
the independently found +/-1e-300 A stamping case. Actual recovery uses a global
absolute current bound; it does not certify relative accuracy of arbitrarily
tiny patches. Requested/recovered currents and raw errors are retained, and
`patch_relative_accuracy_certified=false` prevents an unsupported claim.

## Remaining PI01-S02 conditions

This resolves land transitions only for the declared rectangular prism. Annular
and arbitrary source-backed copper, general nonconforming face mapping and
external barrel/circuit port equations still need their own compilation and
verification. Neumann patches are not equipotential electrodes. Labels never
define circuit topology or silently change an electrode model.

EBrake's finite electrode definition remains unspecified and its original load
is outside planar copper; original density/AC and Marble AC/SI conditions stay
open. No new board solve or convergence pass is claimed by this increment.
Whole-board vector/unique-volume percentiles and original board study acceptance
are still required before PI01-S02 can be marked done. Full-suite, installed
package, physical measurement and release qualification were not run here.
