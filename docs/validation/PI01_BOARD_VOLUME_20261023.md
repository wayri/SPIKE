<!-- SPDX-License-Identifier: Apache-2.0 -->
# PI01-S02: conservative board-volume reference, 23 October 2026

Full stage: **in progress**. Production qualification: **false**. The bounded
offline reference and its reproducible verification are supplementary evidence;
the original EBrake/Marble studies have not passed whole-board acceptance.

## Delivered scope and method

The [independently authored governing derivation](../DC_TETRA_RT0.md),
[independent continuum oracles](../DC_TETRA_RT0_ORACLES.md) and
[ADR 0134](../adr/0134-conservative-board-volume-dc-reference.md) define the
experimental steady scalar Ohmic model. Exact full RT0 tetrahedral mass,
face-trace hybridization and signed conservative face flux reconstruct all
three current components and integrated Joule loss. The independent retained
validator uses degree-two tetrahedral cubature, face integrals and local weak
laws; it does not repeat the field solve.

Source preparation authenticates every native pad/via, maps explicit full-pad
copper surfaces including drill holes, recovers source-filled outer/hole rings,
and builds disjoint copper slabs and explicit plated barrel gaps. Directional
geometry coverage and all supplied physical conductor volume are retained,
including unexcited components. Layer profile, conductivity, plating thickness,
curve approximation and Neumann electrode assumptions remain explicit. This
does not qualify an actual manufactured stack, equipotential electrodes,
noncircular/per-layer barrels, AC/SI or thermal feedback.

Independent review exposed and repaired subnormal heat acceptance, strong-drive
masking of an erased weak disconnected component, and source-request contract
drift during replay. Each connected component now has its own current residual
and heat/work checks. Human numerical release review remains required.

## Verification evidence

The supplemental [source-bound receipt](parity/PI01-S02-board-volume-20261023.json)
binds the exact executed source, tests, fixtures, method documents,
[execution log](parity/PI01-S02-board-volume-20261023.log) and
[raw retained fields](parity/PI01-S02-board-volume-fields-20261023.json).
Its 47 focused tests include independently authored analytical and harmonic
continuum oracles, rotation/translation/units, material layers, multiple driven
and undriven components, physical-volume quantiles, holes, arbitrary finite
contacts and malformed/forged source and result rejection. No skipped test can
pass the gate. The gate's separate self-tests check retained-report rejection.
Executed environment: Windows, Python 3.11.9, NumPy 2.2.6, SciPy 1.17.1,
Shapely 2.1.2 / GEOS 3.13.1. The native-source CLI result was independently
replayed after JSON serialization; an attempted overwrite rejected and left
the existing result's SHA256 unchanged. The broader DC/Marble/solid-geometry
regression run passed 88 of 89 tests initially; its one metadata error used a
hardcoded historical structural receipt despite a newer ledger receipt. The
test now follows the current ledger pointer while preserving the historical
evidence and the same stale-evidence rejection checks; all 15 backlog tests
passed on rerun. Architecture and scoped whitespace checks passed. A complete
repository-wide Python/UI/native/packaging qualification was not executed for
this isolated offline supplement.

For phi=x*y on a unit cube, sigma=1 S/m, the independent exact heat is 2/3 W.
At 6/48/384 tetrahedra, field L2 errors are 1/3, 1/6, 1/12 and heat errors are
1/9, 1/36, 1/144 W. The finest p95/p99 reconstructed-field quantiles differ
from the analytical continuum ranks by approximately 1.64%/1.46%; no monotonic
quantile or continuum-error certificate is asserted. Exact binary64 weighted
ranks retain all supplied physical volume.

The raw report includes the declared holed/multipart board fixture, an
authenticated native SMD-pad source-to-field run, and an authenticated circular
through-pad with annular full-pad electrodes, two land slabs and its barrel gap.
The latter executes 3,840 tetrahedra at target 2 mm: heat
0.0011658274560020045 W, signed terminal work 0.0011658274560042297 W.
Those are discrete witnesses under supplied model assumptions, not measured
hardware validation. The runnable JSON example is
`examples/dc_board_volume/run_volume.py`; existing output files are rejected.

Earlier finite-contact (18), rectangular/axial (23) and annular/circuit (30)
checks were genuinely replayed against current sources. Historical receipts
remain intact; their current ledger pointers identify the fresh executions.

## Current native EBrake and Marble attempts

The owner authorized separate studies with full-pad electrodes and selected
EBrake's **24V** rail. Original point studies and results are preserved. The
new unit-current distributions are explicit transfer experiments, not inferred
device operating loads. Both boards' complete pad/via inventories authenticate
and their before/after native source hashes are unchanged.

| Separate study | Explicit finite electrodes | Prepared source support | Current outcome |
| --- | --- | --- | --- |
| EBrake 24V | J13.1 bottom +1 A; Q2.2/Q4.2/Q6.2/Q8.2 bottom -0.25 A each | 4 layer/net groups, 27 gap volumes, 9 axial sources | 5,000-tetrahedron reference budget exceeded before refinement |
| Marble +1V0 | U1.P14 top +0.5 A; U1.K8 top -0.5 A | 12 groups, 649 gap volumes, 59 axial sources | 512-barrel-gap compiler budget exceeded |
| Marble reviewed net | U37.18 bottom +1 A; R195.1 top -1 A | 12 groups, 11 gap volumes, 1 axial source | 5,000-tetrahedron budget exceeded before mesh allocation |

Native inventory: EBrake 489 pads / 103 vias; Marble 5,272 pads / 3,664 vias.
EBrake SHA256:
`d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca`.
Marble SHA256:
`3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512`.

Fresh attempts are retained under
`build/pi01-board-volume-20261023/ebrake-studies-v2/ebrake-audit.json` and
`build/pi01-board-volume-20261023/marble-studies-v2/marble-audit.json`, including
source-fill proof, exact electrode IDs, model JSON/digests, exceptions and
tracebacks. The supplemental receipt binds those audit files by hash. The
earlier failed attempts in the sibling `*-studies` directories are preserved.
EBrake's 443-point retraced 24V fill has one outer ring and three holes; its
adapter has zero measured directional support loss. No air or copper was
silently removed, no curved/drilled source was replaced with a point, and no
resource or physical acceptance threshold was raised to claim success.

## Next acceptance work, in order

1. Profile native board meshing, source coverage and sparse trace solve. Develop
   a scalable conforming solid/trace path with independent equivalence against
   this retained reference and bounded resource/cancellation tests; avoid the
   current global XY/Z arrangement's unnecessary subdivisions. Increase
   admitted resources only with executed memory, conditioning and geometry
   audit evidence, following the native/HPC roadmap.
2. Reexecute the new explicit EBrake24V and Marble studies through refinement;
   establish physical-volume density and voltage/heat convergence, with source
   stack/material uncertainty recorded. Preserve the original point-study
   failures as separate cases; the replacement studies do not retroactively
   satisfy their unchanged-terminal acceptance.
3. Complete the existing original-board PI01-S02 acceptance and AC/SI gates,
   then integrate a qualified worker/desktop route. Do not mark the full stage
   done or expand its runtime capability claim from offline fixture evidence.
4. Reuse source/cell identities, signed terminal work and per-volume watts for
   conservative thermal/mechanical composition, with separate transfer and
   feedback validation. Broader multiphysics remains sequenced after PI/SI
   closure; this increment provides reusable volume and conservation contracts.

## Reproduction

Run with the project environment (`.venv-emerge3/Scripts/python.exe` here):

```text
python -B scripts/parity_board_volume_gate.py --output FRESH_RECEIPT.json --log FRESH_LOG.log --report FRESH_FIELDS.json --board-audit build/pi01-board-volume-20261023/ebrake-studies-v2/ebrake-audit.json --board-audit build/pi01-board-volume-20261023/marble-studies-v2/marble-audit.json
python -B scripts/benchmark_board_volume_dc.py --board ebrake --output FRESH_EBRAKE_DIRECTORY
python -B scripts/benchmark_board_volume_dc.py --board marble --output FRESH_MARBLE_DIRECTORY
```

All outputs must be fresh repository paths. The Marble source is a local
qualification input, not newly redistributed by this change. This work adds no
dependency, copied external implementation, production solver dispatch or claim
about the frozen worker executable from the coordinating chat.
