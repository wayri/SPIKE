<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Experimental three-dimensional enclosure conjugate heat transfer

This page documents unchanged v1 behavior. The separately selected
[v2 obstacle/refined-momentum workflow](ENCLOSURE_CHT_REFINED.md) adds actual
momentum re-solving on tensor cuts; it does not change v1 limits or enable
turbulence/rotating propellers.

## Executable scope

`run_enclosure_cht` composes three independently checked operators:

1. Uniform staggered-grid incompressible momentum: existing creeping flow
   around supplied voxel solids, or a new steady inertial laminar solve in one
   complete rectangular fluid region (which may have solid walls outside it).
2. [Nested thermal refinement and conservative MAC transfer](ENCLOSURE_REFINEMENT.md).
3. Shared fluid/solid sensible-energy balance, steady or backward Euler transient.

This is an experimental reference workflow, **not general production enclosure
CFD**. Inertial obstacle flow, arbitrary curved CAD, inlets/outlets, fan curves,
buoyancy, turbulence and rotating propellers are not supported by this route.
The creeping branch retains its original Reynolds bound of 0.1; the new inertial
branch has a conservative computed bound of 20. These admission ceilings are
not general physical laminar-transition criteria. Unsupported geometry or
nonconvergence is rejected, never replaced by creeping flow automatically.

## Running the supplied benchmarks and examples

Use a project environment containing the existing NumPy and SciPy dependencies:

```powershell
.venv-emerge3\Scripts\python.exe scripts\benchmark_enclosure_cht.py --help
.venv-emerge3\Scripts\python.exe scripts\benchmark_enclosure_cht.py --output build\my-enclosure-verification
.venv-emerge3\Scripts\python.exe scripts\run_cfd.py --capabilities
```

The benchmark runner writes exact request/result files and a source-bound
receipt to its selected output directory. Run an emitted request separately:

```powershell
.venv-emerge3\Scripts\python.exe scripts\run_cfd.py --engine enclosure-cht `
  --request <request.json> --output <result.json>
```

The process result wraps the domain result in `{"ok":true,"result":...}`.
`ok` means successful dispatch; inspect the domain `status`. CLI exit 3 denotes
a rejected, cancelled or failed domain result; only accepted solves exit zero.
The CLI atomically replaces the output. There is no JSON-supplied executable,
shell command or external mesh path. Standalone module cancellation is polled
between assembly/iteration/step boundaries, not inside sparse factorization;
hard cancellation requires host process termination.

## Input and manual refinement

Contract: `spike/enclosure-cht-request/v1`. All properties are SI values, and
unknown fields are rejected. A coarse `material_ids[x][y][z]` assigns supplied
fluid/solid materials. Exactly one fluid material is admitted; conductivity,
density, heat capacity and fluid viscosity are constant and positive.
`heat_sources_w_m3` supplies heat generation; `body_force_n_m3` supplies an
explicit fluid drive and must be zero in solids. Properties and drive are not
inferred from a PCB, fan or fluid name. Numerical reference-fluid examples do
not validate air, water or a real enclosure operating envelope.

`grid` declares shape, spacing and origin in metres. `local_refinement` accepts
up to 64 user-selected boxes, each with `bounds_m:[[xmin,xmax],...]` and an
integer `split_factor` from 2 through 4. Cuts are nested in original intervals;
materials, volumes and normal face fluxes retain parent identity. **These cuts
propagate as tensor planes across the domain. Momentum remains coarse and is
not locally re-solved.** This is not octree AMR, a locally confined patch or a
boundary-layer mesher. Re-run with finer coarse grids to assess flow accuracy.

Six exterior thermal faces independently select adiabatic, prescribed absolute
temperature, outward convection to a supplied ambient, or supplied inward heat
flux. All exterior **flow** boundaries remain closed and no-slip. Steady energy
requires a resolved temperature or convection anchor; transient energy permits
an adiabatic enclosure with a supplied uniform initial temperature. The initial
flow is already steady: transient momentum/startup is not modeled.

Bounds: 4096 coarse cells, 8192 thermal cells, 64 fine intervals per axis,
256 thermal steps, one million cell-steps and 200000 saved temperature values.
Input and accepted result JSON are each capped at 8 MiB. Geometric arithmetic,
matrix conditioning, residual, mass, energy and positivity checks can reject
smaller requests. Resource counts do not impose an OS sparse-factor fill bound.

## Results and acceptance meaning

Accepted results include fine-grid axes, material IDs, absolute temperature,
shared normal velocities, coarse pressure gauge, thermal history and snapshots,
solid/fluid interface temperatures and signed heat, momentum residual/work,
mass-transfer invariants, and raw/normalized energy defects. Steady heat is in W;
transient accumulated heat and storage are in J. Exterior heat is positive
outward. Interface heat is positive from the lower-index cell to its neighbor.
Gauge pressure zero in a solid is padding, not a physical stress result.

`production_qualified` remains false. Numerical conservation establishes the
discrete accounting, not physical accuracy; upstream upwind thermal transport
can smear temperature gradients. Conductivity/contact geometry uncertainty,
grid/time convergence, independent solver and measured correlation still matter.
Separate smooth conduction and non-tangent advective manufactured fields have
executed spatial-refinement checks; neither substitutes for a real enclosure.
Drive/viscous mechanical work is reported by momentum where available, but is
**not automatically deposited as heat**. No radiation, phase change, electrical
heating inference, property feedback or two-way mechanical coupling is present.

## Next stages: turbulence and propellers

The [staged development plan](INTERNAL_CFD_AND_FSI_PLAN.md) retains separate
acceptance for nonuniform momentum, general obstacle inertia and boundary
conditions before engineering turbulence. RANS needs a precisely versioned
closure, wall distance/treatment, positivity and matched grid/validation cases.
Rotors then require a rotating-frame or conservative moving-mesh formulation,
geometric conservation, torque/thrust/shaft-power and measured operating curves.
No existing flag or successful laminar benchmark enables either capability.

Derivation, reviewed primary sources and repaired accuracy defects are recorded
in [the numerical evidence](validation/ENCLOSURE_CHT_METHOD_20261020.md).
