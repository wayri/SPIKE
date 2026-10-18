<!-- SPDX-License-Identifier: Apache-2.0 -->
# GP07-S01: Bounded static thermoelasticity

Verified on 18 October 2026. Status: **Done for this bounded stage**;
`production_qualified: false`. See the [scope and remaining stages](../COUPLED_MECHANICS_MAGNETICS_DEVICES_PLAN.md).

The original P1 tetra kernel assembles isotropic engineering-strain elasticity,
thermal eigenstrain, nodal loads and prescribed displacement constraints on an
admitted conforming retained mesh. The one-way adapter executes the existing
steady thermal solver and transfers every nodal Kelvin value on an identical
indexed mesh. It preserves original and generated input digests, ownership and
caller context; it does not verify an external CAD revision.

The [source-bound execution receipt](parity/GP07-S01.json) records **16 tests,
zero skips**, with [actual execution log](parity/GP07-S01-lf-reverified.log).
Reproduce using new output paths:

```powershell
.venv/Scripts/python.exe scripts/parity_structural_gate.py --stage GP07-S01 --output build/mechanics-check.json --log build/mechanics-check.log
```

Checks cover rotated affine stress, a uniformly loaded bar's reaction and
elastic energy, metre/millimetre equivalence, free thermal expansion, fully
clamped thermal stress, distinct material reference temperatures, nonuniform
temperature eigenstrain, executed thermal gradient/free expansion, Unicode
ownership digests, public schemas, top-level worker dispatch and failure cases.
Rigid modes, inverted/sliver geometry, unsupported Poisson ratio, malformed
materials/temperatures/forces, resource overruns and cancellation are rejected.

The manufactured displacement `u_x = 1e-4 x²` on the unit cube uses its
independently derived constant body force and prescribed boundary displacement.
Volume-weighted cell-barycentre displacement errors for 1, 2 and 3 subdivisions
are 2.104063528825433e-5, 5.260158822063584e-6 and
2.3378483653615995e-6 metres. Error reductions are 4.0 and 2.25, consistent with
second-order displacement behavior for this smooth test. This does not establish
stress convergence at singularities or general geometry/material qualification.

The executed thermal gradient `T = 300 + 100 x` K produces cell-mean thermal
strain. With every displacement fixed, the normal stress equals
`-E alpha (mean(T)-Tref)/(1-2 nu)` and shear vanishes. Uniform heating with only
rigid modes constrained produces free expansion and near-zero stress. Elastic
energy includes thermal eigenstrain and is not asserted to equal half of
external mechanical work.

A read-only numerical review found no actionable defect in shear conventions,
loads, energy/reaction signs, SI geometry, temperature transfer or digest
binding. It is agent review, not the knowledgeable human numerical review
required before release. Mixed-material interface oracles, near-condition-limit
sweeps, measured references, mechanics UI, nonlinear/contact/dynamic mechanics,
failure/lifetime and general magnetic/device coupling remain open.

Broader focused regression execution passed **206 tests**, zero skips, covering
the retained PI/SI numerical stages, mechanical contracts, thermal solver,
network graph and backlog/evidence guards. Architecture and eight updated
documentation checks passed. Full release checks were not rerun; this record
does not resolve previously documented unrelated full-suite failures.
