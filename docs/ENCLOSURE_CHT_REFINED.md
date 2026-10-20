<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Experimental obstacle-inertial CHT with resolved momentum sizing

## What changes from v1

The opt-in `spike/enclosure-cht-request/v2` uses stationary supplied voxel
obstacles and re-solves steady inertial momentum **on the actual refined
rectilinear grid**. Energy uses those same shared normal faces and cells.
There is no coarse-flow interpolation presented as a refined momentum solve.
The v1 route, schemas, numerical limits and rectangular-inertial restriction
remain unchanged. Old jobs do not silently migrate.

Selected refinement boxes split intersected coarse intervals. Cuts propagate
whole tensor planes: this provides manually controlled momentum/thermal sizing,
**not confined patch, hanging-face or octree AMR**. Obstacles remain staircase
voxels; this is not curved-body conforming CAD or moving blade geometry.
Coarse material IDs, body forces and heat densities are inherited piecewise
constantly. Refining them does not invent finer source or geometry information.

## Running and inspecting a case

Generate and execute the source-bound numerical corpus in a fresh directory:

```powershell
.venv-emerge3\Scripts\python.exe scripts\benchmark_enclosure_cht_v2.py --help
.venv-emerge3\Scripts\python.exe scripts\benchmark_enclosure_cht_v2.py --output build\my-refined-enclosure
```

Run an emitted v2 JSON request through the isolated process interface:

```powershell
.venv-emerge3\Scripts\python.exe scripts\run_cfd.py --engine enclosure-cht-v2 `
  --request <request.json> --output <result.json>
```

The worker method is `run_enclosure_cht_v2` with exactly one `request` parameter.
Explicit flow model: `rectilinear_laminar`, with the same three nonlinear
controls as v1. Fields, positive SI material properties, six thermal boundary
types, steady/transient thermal studies, resource and source rules retain v1
semantics. The request contract and model must both select v2 intentionally.

Read the domain status inside the process `result`; successful dispatch is not
successful physics. A completed result carries actual fine axes, fine normal
velocities, fine pressure gauge, temperature, material identity, momentum and
independently recomputed mass diagnostics, thermal history and interface heat.
CLI exit 3 denotes rejected/cancelled/failed physics. Input and accepted output
are bounded to 8 MiB, including the formatted CLI envelope on publication.
Rejected or cancelled results do not carry accepted fields.

The runner emits `obstacle-coarse-request.json`, `obstacle-refined-request.json`,
`disconnected-hydrostatic-request.json` and `transient-startup-request.json`,
with actual results and a source-bound receipt. For example, run
`build\my-refined-enclosure\obstacle-refined-request.json` through the command
above. Compare coarse/fine unknown counts and fields, not only result status.
The synthetic high-density reference fluid is not an engineering material model.

Pressure is a relative gauge per connected fluid component; zeros inside solids
are padding, not mechanical stress. Compare matching components and gauges when
checking pressure. Independent mass verification recomputes divergence from the
published faces, requires exact zero wall/solid flux and rejects nonfinite
derived arithmetic before energy execution.

## Admission and validity

This is a small sparse-direct numerical reference, not a scalable production
backend. The molecular-property Reynolds admission remains at most 20; no
eddy-viscosity input can bypass it. Metric, cell, conditioning, nonlinear,
mass/work, thermal-energy, positivity and publication budgets remain enforced.
Sparse factorization cannot poll cancellation internally; a hard deadline needs
host process cancellation. Uniform and refined operators require their own
verified error envelopes; conservation alone does not establish grid accuracy.

Momentum is steady. Backward-Euler thermal storage can evolve on the accepted
fixed flow, but there is no transient momentum, temperature-dependent viscosity,
buoyancy or thermal-to-flow feedback. Mechanical drive work is not automatically
deposited as heat. No radiation, compressibility, phase change or FSI is inferred.

See the [independent momentum derivation and executed evidence](validation/ENCLOSURE_RECTILINEAR_MOMENTUM_20261020.md),
[v1 thermal method](validation/ENCLOSURE_CHT_METHOD_20261020.md) and
[ADR 0121](adr/0121-refined-obstacle-inertial-enclosure-cht.md).
Actual matrix, source-bound receipt, accuracy observations and repaired review
findings are in the [v2 validation record](validation/ENCLOSURE_CHT_V2_VALIDATION_20261020.md).

## Turbulence and propellers are separate unfinished methods

The [requirements and primary-source review](validation/TURBULENCE_ROTOR_REQUIREMENTS_20261020.md)
separate a solved turbulence transport law plus variable symmetric stress from
prescribed viscosity, and conservative rotating/moving-boundary physics from
swirl forcing. Neither exists merely because obstacles and grid sizing work.
Closure/wall, rotor-interface/time and thrust/torque/shaft-power tests remain
required, together with matched physical references. Capabilities must retain
false turbulence/rotor and production flags until that work actually passes.
