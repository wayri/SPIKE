# Analysis families and mesh development

SPDX-License-Identifier: MIT  
Copyright (c) 2026 SigHarmonic

## Selection strategy

Use the formulation appropriate to the requested quantities, material model,
electrical size and boundary conditions. Do not silently substitute a network
approximation for a requested full-wave field solve.

| Analysis need | Intended formulation and discretization |
| --- | --- |
| DC PI, resistance, electrostatics, quasi-TEM extraction | Conduction/Laplace FEM or suitable boundary formulation; volume/surface meshes and explicit terminals |
| SI/PI broadband and transient networks | PEEC/RLGC, passive N-ports, circuit/transient convolution; mapped conductor/network discretization |
| Open-region antenna/scattering problems | Surface MoM with RWG EFIE; closed-surface MFIE/CFIE where applicable; oriented triangular surface mesh |
| Inhomogeneous 3-D RF/EMI/optical wave fields | H(curl) FEM or FDTD; tetrahedral/hybrid volumes or suitable Cartesian grids, modal ports and open boundaries |
| Thermal and electrothermal fields | Conservative heat transport coupled to electrical losses; material-conforming volume meshes |
| Enclosure airflow/conjugate heat transfer | Conservative flow and energy discretization, wall/boundary-layer resolution, inlet/outlet and fan models |

This table is a development architecture, **not an advertisement that all rows
are complete**. Public `spike.mom_surface` remains unavailable: a basis library
does not solve Maxwell's equations. Other broad workflow limitations remain in
`DEPLOYABLE_SOLVER_PROGRAM.md` and `ENCLOSURE_PCB_INCREMENT.md`.

## Implemented mesh increment

- `AnalysisSpec.mesh.local_controls` now drives actual hybrid track subdivision.
  `spike/local-track-mesh-controls/v1` supports source-ID intervals with local
  target lengths and exact manual split fractions. Overlapping targets use the
  finest size; uncontrolled tracks preserve previous discretization. Unknown
  sources, collapsing nodes and excessive subdivisions are rejected. These
  controls do not move CAD geometry or constitute a 3-D mesh-editing UI.
- `refine_tetra_mesh` bisects the full incident-cell star of selected edges of
  supplied conforming tetrahedra. Shared midpoints prevent new hanging faces.
  Material IDs, source ownership and labeled exterior faces are preserved;
  child-to-original-cell ancestry is returned. It supports skew/non-cuboidal
  tetrahedra, not just cube subdivisions.
- `optimize_tetra_mesh` uses bounded backtracking interior smoothing. Exterior,
  material-interface and caller-protected vertices remain fixed. Accepted moves
  improve the minimum incident mean-ratio quality; positive volumes, total
  volume and nondecreasing global minimum quality are checked. Refinement itself
  is **not** guaranteed to improve element shape. Recompute operators/results
  after either operation; solution transfer is not implemented.
- Both volume operations follow the existing `spike/solver-mesh/v1` schema.
  The OpenFOAM handoff is tested with synthetic converter admission evidence;
  refinement does not issue production qualification or run CFD.
- `mom_surface_basis.py` supplies immutable oriented triangular topology and
  full interior-edge RWG basis evaluation/divergence. Tests cover tangency,
  normal-current continuity, divergence balance, Gram positive definiteness,
  numbering invariance and dimensional scaling. Boundary half-RWGs are absent.

The tetrahedral operations assume an initially conforming, nonoverlapping mesh.
Local face/topology checks do not establish global intersection freedom or
heal arbitrary imported CAD. RWG topology checks likewise do not establish
geometric intersection freedom.

## Next implementation order

1. Tagged CAD/PCB geometry generation with holes, via/antipad structures and
   conforming material/terminal interfaces; explicit CAD surface projection.
2. Geometry-based local sizing and protected-region controls, sliver removal,
   high-order curved elements, boundary-layer prisms and adaptive error-driven
   refinement with conservative solution transfer.
3. Dense Galerkin MoM reference: singular/near-singular quadrature, EFIE,
   incident waves and feed models, then PEC sphere/Mie and dipole convergence.
   Add MFIE/CFIE only on their applicable closed surfaces, followed by dielectric
   transmission formulations. Keep field-solver capability off until validated.
4. Stabilization and scalable execution: low-frequency/dense-mesh conditioning,
   matrix-free FMM/MLFMA, suitable preconditioning, then distributed benchmarks.
5. Hybrid FEM/BEM/circuit/thermal coupling with explicit transfer contracts,
   energy checks, independent-solver and measured correlation.

Modern methods are evaluated against reproducible accuracy/memory/time tests,
not adopted merely because they are newer. Gmsh documents local sizing,
Delaunay/HXT and optimization options; it is a candidate CAD-meshing dependency,
not an installed/admitted component of this increment. [Official manual](https://gmsh.info/doc/texinfo/gmsh.html)

RWG terminology and compatible Maxwell spaces follow mathematical definitions,
not copied implementation. [Bempp function-space documentation](https://bempp.com/handbook/api/function_spaces.html)
Layered-medium Maxwell FMM research is a future PCB scaling candidate, not
evidence of SPIKE performance. [2025 primary paper](https://arxiv.org/abs/2507.18491)

## Running and inspecting

```powershell
python examples/mesh/run_mesh_upgrades.py --output build/my-new-mesh-example
python scripts/verify_mesh_upgrades.py
```

The example writes `mesh.vtu`, schema-compatible mesh JSON, boundary labels,
local track settings and hashes. In the executed skew-tetra example, optimization
raised minimum mean-ratio quality from `0.04481` to `0.35875` without changing the
exterior; subsequent requested edge refinement gave `0.29853` and conserved
volume. This is one controlled example, not a claim of universal superiority.

The example also builds nine closed-surface RWG functions with integrated
divergence cancellation to roundoff and a 35-branch locally refined track with
unchanged 10 mm length. No MoM or FEM field solve is claimed by these results.

Local checkpoint: **52 tests passed with warnings as errors**, plus architecture
checks. The example completed one warmup and five measured runs (median 1.504 s,
including interpreter startup and artifact I/O). Source hashes remained stable.
Evidence: `build/mesh-evidence-20260906T171352.498209Z/report.json` and its
`SHA256.json`; inspectable example mesh: `build/mesh-upgrade-example-20260906/mesh.vtu`.
An independently identified subnormal-volume admission defect is covered by a
permanent rejection regression. No general performance baseline or production
solver qualification is inferred from this checkpoint.
