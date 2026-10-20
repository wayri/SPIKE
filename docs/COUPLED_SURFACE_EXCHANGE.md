<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Conservative coupled-surface exchange

## Bounded claim

`python/spike_core/coupled_surface_exchange.py` is an experimental, solver-neutral
transfer kernel for a caller-supplied nonmatching surface partition. It maps a
piecewise-constant source heat flux in `W/m2` to destination-face integrated heat
rates in `W`, or a piecewise-constant source traction in `N/m2` to
destination-face integrated forces in `N`. With a complete valid overlap
partition, the raw outward totals are equal and opposite to floating-point
roundoff. An optional destination temperature, displacement, or velocity field
is mapped back by the adjoint pair.

This is only a first transfer foundation for future CFD-to-thermal or
CFD-to-structure work. It is not a CFD solver, structural solver, conjugate heat
transfer solve, moving-mesh method, two-way coupling/time master, strong or weak
FSI iteration, aeroelastic/flutter analysis, or full FSI capability. It changes
no execution or completion gate.

## Contract and sign convention

Call `transfer_coupled_surface_exchange(request, cancel_check=None)` with
`spike/coupled-surface-exchange-request/v1`, or pass UTF-8 JSON to
`parse_coupled_surface_exchange_json`. The latter rejects duplicate JSON object
keys. All nested objects reject unknown and missing keys. Booleans are not
numbers; all areas and field values must be finite; all areas must be positive.

The request fields are:

- `transfer_id`, `quantity` (`heat_flux` or `traction`), and the required
  `normal_relation: opposite_outward_normals`;
- exact `units`: `length: m`, `area: m2`, and either `W/m2` to `W` or `N/m2`
  to `N`;
- `source_patch` and `destination_patch`, each with `participant_id`, `patch_id`,
  lowercase SHA-256 `geometry_digest`, an explicit
  `{id, rank: 3, handedness: right}` frame, and positive `{id, area_m2}` faces;
- sparse `{source_face_id, destination_face_id, area_m2}` overlaps;
- `context_digest`, computed by `coupled_surface_context_digest`, and complete
  source-face values; and
- optionally, complete destination-face values plus `destination_value_unit`.
  Heat accepts only `K`. Traction accepts `m` (virtual work) or `m/s` (virtual
  power). The unit is never guessed from numeric values.

The two frame objects must be identical. The kernel does not transform vectors.
Geometry hashes and overlap areas are caller assertions: the digest binds the
identities and data but does not authenticate CAD or prove geometric correctness.
Changing either patch identity, its geometry hash, units, frame, face areas, or
the overlap map without updating `context_digest` fails as stale data.

Both participants use outward-positive conventions and opposite outward normals.
Thus positive heat leaving the source is negative outward heat at the destination.
Likewise, an outward traction acting on the source maps to the equal-and-opposite
Cartesian force acting on the destination. Inputs that instead mean "force
exerted by the source on the destination" must first be converted by the caller;
the kernel does not infer semantics from a solver name.

Every face and overlap area must be at least the minimum positive *normal*
binary64 value, `2.2250738585072014e-308 m2`. Subnormal geometry coefficients
are rejected even though they are positive, because their relative precision is
not adequate for coverage and transfer weights.

The result is `spike/coupled-surface-exchange-result/v1`, remains
`status: experimental` and `production_qualified: false`, and reports each
destination integrated value, the canonical context and request digests, raw
global balance, coverage defects, and optional adjoint pairing. It does not
silently alter one face to force a zero residual.

## Independent derivation

Let source faces be indexed by `s`, destination faces by `d`, and let
`O_sd > 0` be the supplied physical overlap area. Let `A_s` be the diagonal
matrix of source-face areas. Admission requires the two exact partitions

```text
sum_d O_sd = area(source face s)
sum_s O_sd = area(destination face d).
```

The implementation uses relative tolerance `1e-12` and zero absolute tolerance
only to admit ordinary binary floating-point sums. It neither clips an overlap
nor renormalizes a row or column. Missing, excess, duplicate, negative, or
unknown-face overlaps fail.

For source outward intensive values `q_s`, destination outward integrated loads
are

```text
L_d = -sum_s O_sd q_s,                 or L = -O^T q.
```

Consequently, complete source coverage gives

```text
sum_d L_d = -sum_s area_s q_s,
```

component by component. For a destination intensive/kinematic field `x_d`, the
reverse map is the overlap average

```text
x_s = sum_d (O_sd / area_s) x_d,       or x_source = A_s^-1 O x_destination.
```

It follows directly, without a fitted correction, that

```text
sum_s (area_s q_s) dot x_s + sum_d L_d dot x_d = 0.
```

For traction paired with metres this is zero net interface virtual work; paired
with metres per second it is zero net interface virtual power. For heat flux
paired with kelvin it is only the bilinear adjoint identity, with formal unit
`W*K`. It is not thermodynamic work, entropy production, a temperature-continuity
condition, or evidence of a qualified thermal interface.

The same sparse triples drive both directions, so the relation is an algebraic
transpose by construction. Work and storage are `O(number of faces + number of
overlaps)`; no dense source-by-destination matrix or quadratic face-pair search
is formed.

The implementation evaluates each nonzero product from binary mantissas and a
combined exponent. The reverse term combines the mathematical
`(O_sd / area_s) * x_d` operation without first forming `O_sd*x_d`, so a small
area cannot silently erase a representable mapped value and a large area cannot
cause a false intermediate overflow. A nonzero exact load, reverse term, or
pairing that rounds to zero is rejected with `COUPLED_SURFACE_UNDERFLOW`; an
unrepresentable finite-range overflow is rejected with `COUPLED_SURFACE_RANGE`.
No fabricated zero enters conservation or adjoint diagnostics. Signed totals
use `math.fsum`; if its intermediate overflows, a bounded exact dyadic-rational
sum distinguishes representable cancellation from a genuinely invalid range.

## Source ledger and clean-room record

Retrieved 2026-10-20.

| Source | Exact extent reviewed | Foundation used and applicability limit |
| --- | --- | --- |
| C. Farhat, M. Lesoinne, P. Le Tallec, *Load and motion transfer algorithms for fluid/structure interaction problems with non-matching discrete interfaces: Momentum and energy conservation, optimal discretization and application to aeroelasticity*, Computer Methods in Applied Mechanics and Engineering 157 (1998) 95-114, [DOI 10.1016/S0045-7825(97)00216-8](https://doi.org/10.1016/S0045-7825(97)00216-8) | Publisher DOI/title metadata and reproduced article text: Section 2.2.1, equations 9-15 and surrounding virtual-work derivation on pp. 102-103; Section 3, equations 21-24 and surrounding motion-transfer discussion on pp. 106-108. | A displacement interpolation operator and the corresponding transpose load operator preserve discrete interface energy/work. The paper addresses broader FE/FV nonmatching FSI interfaces. SPIKE independently specializes only that adjoint principle to supplied piecewise-constant overlap areas; it does not implement the paper's pairing, FE shape-function, mortar, time-coupling, or aeroelastic algorithms. |
| preCICE project, *Mapping configuration*, current online documentation, [official page](https://precice.org/configuration-mapping) | Sections defining conservative, consistent, and scaled-consistent mapping, read 2026-10-20. No source code inspected. | Corroborates current coupling terminology: extensive forces need conservative mapping while intensive temperatures use a consistent mapping. It is terminology/design guidance, not validation of this implementation or a substitute for the paper's derivation. |

The equations, schema, code, test geometry, and expected values here were authored
independently in SPIKE notation. No external implementation source, examples, or
test data were copied or adapted.

## Verification evidence

`tests/python/test_coupled_surface_exchange.py` contains independently computed
small arithmetic oracles:

- a nonuniform split/merge map with source areas 2 and 1 square metres and
  destination areas 1.5 and 1.5 square metres checks exact integrated heat and
  reversed outward signs;
- a three-component traction case checks resultant force and transpose-paired
  virtual work/power;
- a reverse nonuniform temperature average checks the algebraic duality label
  without promoting it to physical thermal work; and
- the review counterexample `area=1e-300 m2`, `q=1e300 W/m2`, and
  `temperature=1e-30 K` checks destination load `-1 W`, reverse value `1e-30 K`,
  and paired values `+/-1e-30 W*K`; a corresponding `1e300` area case checks
  that a representable reverse value survives what would otherwise be an
  overflowing intermediate product; and
- rejection cases cover incomplete/excess coverage, duplicate and negative
  overlaps, NaN and boolean numbers, duplicate face/value identities, unknown
  fields, non-SI units, unsupported pressure, frame rank/mismatch, malformed
  geometry digest, stale context, missing explicit destination units, face,
  overlap and byte budgets, subnormal geometry areas, nonzero load/pairing
  underflow, output overflow, duplicate JSON keys, and cancellation.

These are code-verification fixtures, not physical validation. Knowledgeable
human numerical review remains mandatory before release. No independent CFD/FEM
comparison, measured interface data, convergence study, uncertainty assessment,
or production-scale evidence has been completed.

## Numerical and operational limits

- At most 512 source plus destination faces, 8,192 overlap triples, and 8 MiB
  per input or result JSON record are admitted.
- Cancellation is checked before validation, periodically during sparse-map
  validation/application, and before return. Cancellation returns no partial
  exchange. Process-level resource containment remains the worker's concern.
- Geometry areas below the minimum normal binary64 value fail. Products and
  sums outside representable binary64 range fail; nonzero products that would
  silently become zero also fail. Areas at the admitted lower bound and extreme
  overlap ratios can still be poorly conditioned physical data. The kernel
  reports raw defects and does not rescale or reinterpret the problem.
- The map is piecewise constant on supplied faces. It provides no higher-order
  reconstruction, limiter, gradient transfer, temporal interpolation, or moving
  overlap update.
- There are no face coordinates or normals. Scalar pressure is intentionally
  unsupported because converting it to traction requires a trusted normal.
  Resultant force is conserved componentwise, but interface moment is neither
  computed nor claimed. A geometry-aware moment-conserving transfer needs
  separately reviewed coordinates and constraints.
- Exact overlap coverage alone does not prove correct contact topology,
  orientation, interface coincidence, mesh quality, CFD wall stress accuracy,
  structural load accuracy, temperature continuity, or coupled stability.
