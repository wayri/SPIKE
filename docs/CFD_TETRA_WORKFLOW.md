<!-- SPDX-License-Identifier: Apache-2.0 -->
# Tetrahedral CAD / open-flow research workflow

This is an experimental, in-process development workflow. It is not a new
public worker engine or qualified engineering turbulence/CHT capability.
The [execution record](validation/CFD_CAD_OPEN_BOUNDARY_20261021.md) distinguishes
actual native CAD runs from mathematical unit tests and retained failed probes.

## Run the independently authored CAD examples

From the repository root, using the existing admitted optional OCC environment:

```powershell
.venv-emerge3/Scripts/python.exe -Werror scripts/generate_cfd_step_fixtures.py --output build/my-cfd-step-fixtures
.venv-emerge3/Scripts/python.exe -Werror scripts/benchmark_cad_cfd_open_flow.py --fixtures build/my-cfd-step-fixtures --output build/my-cad-cfd-results
```

Output directories must be fresh. The generator retains STEP files, generator
and input hashes, pinned runtime identity and process-containment diagnostics.
The benchmark retains each native mesh request/result, explicit surface map,
SI numerical mesh, flow and energy requests/results, analytical errors and
selected source/artifact hashes. Nonzero exit status is a failed qualification,
including a source change during execution; never refresh its hashes to pass.

Examples are a rectangular prism, affine-sheared prism, and cylinder. Their
known plane equations define inlet/outlet tags; this is **not automatic fluid
domain or boundary-condition inference**. Prescribed side velocities are
manufactured solution data, not no-slip walls for a physical square duct/pipe.
The cylinder is an affine patch test on faceted geometry, not a pipe friction
validation or proof of curved-boundary convergence.

## Use an already prepared numerical tetrahedral mesh

The numerical API is `admit_cfd_tetra_mesh` in `cfd_tetra_mesh.py`:

```text
contract: spike/cfd-tetra-mesh/v1
units: m
vertices: finite [x,y,z] coordinates
cells: positively oriented tetrahedra, four vertex indices each
boundary_patches: patch ID -> exterior triangles, exactly once
```

It does not silently fix orientation, weld vertices, generate an enclosure
air volume, or infer materials. Positive-volume overlap screening does not
prove conformity at nonshared zero-measure contacts. See the
[geometry derivation and limits](validation/CFD_TETRA_MESH_20261021.md).
For actual OCC output, `prepare_cfd_tetra_mesh(result, assignments)` requires
an explicit integer CAD-surface-tag to patch-ID mapping and preserves source
lineage separately. Its present bridge accepts only one material and no CAD
interfaces. Numerical thermal material masks do not extend that CAD scope.

`solve_cfd_tetra_stokes` accepts named face-average velocity and **pseudo-traction**
data. It solves constant-property creeping flow with a vector-Laplacian
operator, bounding-box Reynolds bound <=0.1, per-cell conservation and fixed
residual/energy/conditioning limits. It is not symmetric-stress traction or an
inertial stable-open-boundary solver. The [Stokes record](validation/CFD_TETRA_STOKES_20261021.md)
defines units, exact input keys, pressure gauges and backflow rejection.

`solve_cfd_tetra_energy` solves steady RT0/P0 conduction with shared-face upwind
enthalpy on the same mesh. Explicit phases, conductivities and conservative
mass flux are required; solids have no mass flow. Shared flux orientation is
outward from the first face owner. The [energy record](validation/CFD_TETRA_ENERGY_20261021.md)
derives material-interface continuity, inlet temperature and Robin data.
Mapping solved flow into this API is one-way, constant-property coupling,
not buoyancy, a nonlinear fluid-property iteration or turbulent heat transfer.

## Required next stages, in dependency order

1. Complete CAD fluid-volume extraction, conforming multiple materials,
   nonshared contact qualification, boundary-layer meshes and locally controlled
   refinement that preserves every patch/interface. Existing mesh refinement
   tools are not blanket qualification of those operations for this flow path.
2. Add verified physical symmetric stress, general obstacle inertia and stable
   open-boundary treatment on that topology. Retain pressure-gauge, mass,
   work and refinement tests; include recirculation/outlet-domain studies.
   Establish discrete coercivity/Korn control and pressure stability for the
   chosen stress space; do not promote a mere operator substitution.
3. Qualify an exact turbulence variant against matched primary experimental
   and independent-code references, including wall distance, inlet state,
   y-plus, mesh/domain studies and model-form limits. Existing manufactured
   mean/SA equation checks do not establish that qualification.
4. Qualify turbulent conjugate heat transfer with explicit thermal closure,
   wall/interface treatment, conjugate energy and measured heat-transfer data.
   A turbulent Prandtl-number input alone cannot qualify a model.
5. Integrate the transferred circuit/thermal/airflow request: explicitly map
   every circuit loss to retained physical volumes, iterate R(T) using
   unrelaxed fixed-point residuals, publish one consistent accepted state, and
   reject runaway/nonconvergence. Then test geometry-aware streamlines and
   transparent solid overlays against actual solved examples. Existing partial
   desktop edits are not evidence this circuit-coupled workflow is implemented.

No gate is removed by this document. Production availability, general CAD
aerodynamics, engineering turbulence, turbulent CHT and circuit feedback remain
unqualified until their corresponding evidence exists. Knowledgeable human
review is still required before release of numerical changes.
