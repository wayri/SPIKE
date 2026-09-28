<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# PEEC foundation increment (2026-09-28)

Status: experimental implementation and focused verification only. This is
not a Marble AC correction, PI/SI sign-off, or a release qualification.

## Local copper refinement

`spike/conforming-local-refinement/v1` permits at most 64 layer/net-scoped
rectangular refinement regions for the retained interior conforming copper
partition. Region boundaries are inserted exactly into the existing rectangle
partition, then only covered pieces are subdivided. The copper union, finite
pad/via contacts, and global target remain unchanged. Invalid, ineffective,
or over-budget requests fail closed. The rule is deterministic but is manual
spatial control, not an a posteriori error estimator. It cannot recover
boundary copper already omitted by the rectangular partition.

The manufactured sheet tests check exact represented-area preservation,
contact identity, no out-of-copper branch support, repeatability, target edge
limits, and rejection cases. They do not assert that an R/L/C engineering
quantity has converged on Marble.

The legacy Marble contact-perturbation diagnostic fixture was updated to its
current 4.926689 mOhm baseline after the separately committed retained-short-
face mesh correction (`77f297c`). This is a reproducibility expectation for
that approximate graph, not evidence that its AC copper-support problem is
solved. The reduced-contact-loss experiment and MNA residual checks remain.

## RT0 system reduction

The experimental hybridized RT0 DC probe now eliminates center-fan spoke
trace potentials by an exact Schur complement within each original rectangle.
Original rectangle IDs are distinct from shared terminal contact node IDs.
All eliminated traces are reconstructed before the existing local/global
KCL, face-flux, residual, and dissipation-energy checks. The original
hybridized solve remains available as an equivalence oracle with
`condense_spokes=False`. A manufactured three-rectangle fixture reduced the
factorized global unknown count from 21 to 9 at matching resistance and
energy. This changes algebraic cost, not the physical discretization.

The full uncondensed sparse system is still assembled before spoke
elimination; memory and local Schur fill remain bounded by separate guards.
The resource improvement does not prove Marble refinement convergence or
admit a previously blocked board without a fresh audited run.

The pinned Marble 1/0.5/0.25 mm audit with the same half-size interior rule
completed all three solves. It returned 4.472842/4.296649/4.193589 mOhm,
unchanged from the previous numerical sequence to displayed precision.
Retained/factorized global unknowns were 56,897/59,777/66,297 versus
145,227/152,714/170,125 before spoke elimination. Maximum relative
residual was below 4.8e-11, cell KCL below 4.3e-12 A, face KCL below
7.0e-11 A, and relative energy error below 3.5e-11. The consecutive
resistance changes are **4.10% and 2.46%**; the required two-step 2% gate
still **fails**. Machine-readable local evidence is
`build/validation/peec-rt0-condensed-final-20260928.json` (ignored build
output); its four recorded source hashes and pinned board hash were checked
against the files after the run. Report SHA-256:
`919635cb773bbb681e1f07fbbdde063b6df96f48d4a69cf43784ebbc9ff23af9`.

A second pinned audit refined the retained rectangle interiors to one-quarter
of each nominal target edge and used 0.5/0.25/0.125 mm nominal sizes. All
three sparse DC solves completed with 96,047/114,126/174,358 triangles and
61,355/71,494/105,039 factorized global unknowns. Resistance was
4.193713743/4.139103920/4.108510628 mOhm. The consecutive changes were
**1.3194% and 0.7446%**, so this specific two-step **DC resistance** gate
passes. The maximum reported relative linear residual was 3.87e-10 and
relative dissipation-energy error 6.62e-11. The retained-area and contact
approximations remain; this is not an AC L/C or multiport convergence result.
The ignored machine-readable local report is
`build/validation/peec-rt0-condensed-fine-20260928.json`, SHA-256
`7c3acf2ba745b605b1182bb09ec1346d2f0b8a8390d12c879be7c067daf821a1`.
Its recorded board and four source digests matched the files after the run.
To reproduce from the repository root with the pinned local Python environment:

```powershell
build\qualification-py311\Scripts\python.exe scripts\audit_peec_rt0_refinement.py --board build\marble-qualification\sources\Marble-v1.4.4\design\Marble.kicad_pcb --sizes 0.5 0.25 0.125 --max-unknowns 250000 --max-triangles 250000 --interior-edge-factor 0.25 --output build\validation\peec-rt0-condensed-fine-20260928.json
```

The input board and Python environment under `build/` are local ignored
artifacts, not redistributable or clean-machine qualification inputs.

## Separated annular magnetic interactions

The native volume matrix now admits a bounded subset of noncoaxial straight
annular current pairs. For two centrally symmetric finite annuli separated
by center distance `D`, it integrates the degree-0/2/4 terms of the Legendre
expansion using exact volume moments. If the sum of enclosing radii divided
by `D` is `q <= 1/4`, the omitted degree-6-and-higher series is bounded by
`mu*l1*l2*|u1.u2|/(4*pi*D) * q^6/(1-q^2)`. See the
[NIST DLMF generating function](https://dlmf.nist.gov/18.12.E11) and
[Legendre magnitude bound](https://dlmf.nist.gov/18.14.E1).
The reported error also includes a conservative floating-point allowance,
but it is **not a certified interval enclosure**. The pair is admitted only
when that total estimate meets the requested tolerance. Nearby skew or
offset annuli still fail as unsupported. Exactly coordinate-perpendicular
annuli have zero mutual `J1 dot J2` coupling and are admitted as such.

Direct six-coordinate quadrature test oracles cover parallel, skew, reversed,
near-admission-limit, and SI-scaled cases. The strict MSVC C++ build and
three focused native tests passed. These checks establish a bounded
implementation slice, not arbitrary-via board accuracy. The desktop Python
native module and packaged worker were not rebuilt in this increment.

## Regression status

After correcting two stale tests against already-changed project state, the
final local Python 3.11 suite passed **2,103 tests, 2 skipped**. One stale Marble
test still expected the pre-`77f297c` graph baseline; the other expected a
legal-ownership blocker that the current SigHarmonic/MIT release evaluator
correctly no longer emits. The remaining CI, clean-machine, dependency, and
signature release blockers were not waived. The complete native MSVC build
and CTest run passed **19/19** after building all test targets in the Visual
Studio developer environment. `scripts/check_architecture.py` passed after a
concurrent extension-service split brought its module below the size guard.
These local passes do not replace Linux/CI, package parity, field correlation,
or human numerical review.

## Remaining gates

- AC rectangular bases still need a geometry-consistent conforming current
  representation. A copper-area preview or a refined DC grid does not fix
  their physical support or normal-flux continuity.
- The Marble AC R and L convergence, C/source/via coverage, port and
  return definitions, independent correlation, and knowledgeable numerical
  review remain required. See [the active repair record](PEEC_REFINEMENT_REPAIR.md).
- The new correlation-manifest validator checks evidence identities and
  bookkeeping only. It does not compare measured and solved values or grant
  sign-off.
