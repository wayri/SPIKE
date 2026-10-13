<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Retained assembly field meshes and thermal analysis

For the executable steady DC temperature-feedback extension and admitted
averaged electrical losses, see [coupled electrothermal analysis](ASSEMBLY_ELECTROTHERMAL.md).

This workflow transfers supplied conforming tetrahedral volumes for every
physical board and mechanical occurrence into a bounded, solver-neutral world
mesh. It supports an executable experimental steady solid-thermal solve and
explicit EM/SI material and signal/return port metadata. It does **not** yet
translate arbitrary retained assemblies into a Maxwell or PCB channel solver.
Existing reduced multiboard workflows retain their own scope and status.

## Geometry and identity

Use `spike/assembly-field-handoff-request/v1` with `assembly`, `domain`,
`bodies`, `materials`, and optional EM/SI `ports`. Each body binds
`occurrence_id` to the exact retained board `design_id` or part `model_id`
through `reference_id`. Provide a lowercase `source_sha256`, a complete
`spike/solver-mesh/v1` tetra mesh, all exterior `boundary_faces` as
`{id, vertices}`, and an exact local-to-physical `material_map`.
Each board also requires `stack_binding: {id, source_sha256}`. Different board
occurrences retain distinct stack bindings and material mappings.

Source and stack hashes are declarations supplied by the caller. They bind
this request but are not authenticated against an installed CAD asset, and
do not prove that the supplied mesh represents the complete CAD or layer stack.
Never use a rendered board, STEP filename, or stack ID alone as physical volume
evidence. Automatic general CAD-to-conforming-volume construction remains open.

The assembly root must be an identity, right-handed millimetre frame. Every
occurrence placement must be proper rigid; nested parent placements are
composed exactly once. Local mesh coordinates may use metres or millimetres.
Output coordinates use metres. Per-cell Jacobians, inverse Jacobians and volume
ratios must agree with the rigid placement within a relative `1e-9` tolerance;
a conserved aggregate volume cannot hide distorted individual elements.

Cell, source, material and boundary IDs are deterministically namespaced by
occurrence. Duplicate design instances never share solver nodes implicitly.
`source_traceability` retains local-to-global maps, vertex ranges, resolved
placements, input mesh digests and retained asset references. Model-less
subassembly hierarchy nodes are explicitly excluded, with their transforms
recorded; physical structures cannot be omitted.

Per-body admission checks positive tetrahedra, complete labelled exterior faces
and source/material coverage. A bounded separating-axis test rejects positive
inter-occurrence volume overlap, allowing coincident contact surfaces with
separate nodes. These floating-point checks are not exact CAD certification.
The thermal kernel adds bounded cell-overlap and hanging-node checks; general
conformity remains an input obligation, not a certified mesher claim.

## Mesh refinement for different physics

The [internal mesh engine](INTERNAL_MESH_ENGINE.md) provides indicator/manual
refinement and interior optimization. The [focused board volume workflow](PCB_FOCUSED_VOLUME_MESHING.md)
retains full planar PCB geometry with fine selected-net/source regions and a
coarse background. General conforming PCB generation still uses its separately
admitted external development mesher, not the convex internal point generator.

Refine individual occurrence meshes **before** handoff. Relabel every new
exterior triangle and update source maps. Matched thermal contact triangulations
must be refined consistently on both sides and rebound through explicit face
pairs; nonmatching contact projection is unsupported. A refinement changes
request/result identity and requires a fresh solve. Scalar field transfer is
not an H(curl) electromagnetic transfer operator.

SI/EM refinement must resolve copper thickness, via/contact geometry, return
paths, port fields, and the relevant wavelength/skin-depth scales. Thermal
refinement must resolve temperature gradients, material interfaces, contacts
and thin structures. These are different error requirements even when the
geometry and source IDs are shared. This workflow supplies no automatic common
multiphysics error estimator or cross-domain qualification.

## Executable steady thermal problem

Call `run_assembly_field_thermal(request, problem)`. The problem contract is
`spike/assembly-field-thermal-problem/v1` and requires three arrays:

- `boundaries`: each entry names `face: {occurrence_id, face_id}` and a `type`.
  `temperature` uses `temperature_k`; `heat_flux` uses `heat_flux_w_m2`
  positive inward; `convection` uses `heat_transfer_coefficient_w_m2k` and
  `ambient_temperature_k`; `adiabatic` has no parameters. `radiation` uses
  `emissivity` in [0,1] and `radiation_temperature_k`. `convection_radiation`
  requires all four convection/radiation parameters and applies both on one
  face. Radiation is exchange with prescribed infinite isothermal surroundings,
  with outward flux `epsilon*sigma*(T^4-Tr^4)`, not enclosure radiosity. A face
  cannot be reused for another boundary or contact. Radiation temperatures,
  all fixed temperatures and convection ambient temperatures in a radiation
  solve must be in (0,10000] K; every computed node has the same bound.
  This numerical envelope does not establish material validity.
- `heat_sources`: `{occurrence_id, cell_id, heat_source_w_m3}` entries are
  constant over each named local cell. Unlisted cells have zero source.
- `contacts`: each names a retained `contact_id`, positive
  `thermal_contact_conductance_w_m2k` and `face_pairs: [{left, right}]`, where
  both endpoints are occurrence-scoped exterior face references. Endpoints
  must match the retained contact in order. Pair coordinates must coincide and
  exterior normals must oppose. Provided area/conductance must agree with any
  retained contact area/resistance. Perfect or nonmatching contacts fail.

Thermal materials require `id`, `provenance` and
`thermal_conductivity_w_mk`, either a positive scalar or a symmetric positive
definite `3x3` tensor with condition ratio at most `1e12`. Tensors are expressed
in occurrence-local axes and rotated into world axes exactly once. Each
disconnected thermal component needs a temperature/convection/positive-emissivity radiation anchor or a
contact path to one. Unspecified exterior faces are explicitly reported
adiabatic; this is not a guessed ambient boundary.

The independently authored P1 formulation solves `-div(k grad T) = q`.
Its element matrix is `V B k B^T`, volume load is `V q / 4`, and exact triangle
mass is `A (I + 11^T) / 12`. A contact adds the reciprocal positive energy
`h [M,-M;-M,M]`. Diagonally scaled sparse CG solves the constrained system.
Ambient radiation adds the exact P1 triangular weak load
`integral(N_i*epsilon*sigma*(T^4-Tr^4))` and consistent Jacobian
`integral(4*N_i*N_j*epsilon*sigma*T^3)`. Both degree-five polynomial
integrals use a positive 4x4 Gauss rule after the Duffy triangle map, including
its Jacobian. This preserves symmetry and nonnegative tangent energy at
positive Kelvin. Original derivation and fixtures were independently authored;
no external implementation was consulted. `sigma=5.670374419e-8 W/(m2 K4)`.
Damped Newton uses at most 80 steps, each with at most 30 backtracks and a
bounded diagonally scaled CG tangent solve. Acceptance uses the full nonlinear
free-node residual, not the size of a damped update. Singular, out-of-range or
nonconverged states raise an error rather than returning a field.

Results include nodal kelvin temperatures, cell Fourier flux `-k grad T`
in W/m2, contact transfer, boundary reactions, heat balance, residual,
reciprocity, element conditioning, iteration count and resource usage.
Heat balance now includes `radiation_outward_w`; diagnostics include
`newton_iterations`. Saved v1 results lacking these additive fields remain
admissible, treating missing radiation heat as zero. New saved results must
include radiation in conservation; changes to boundary values invalidate the
problem digest. The status is always `experimental`, never production-qualified.

Saved results from the earlier intersection audit used an x-sweep diagnostic
count that included pairs belonging to the same occurrence. Admission can
reconstruct that exact old count in O(N log N), subject to its original 250,000
comparison limit. Only the exact reconstructed legacy handoff digest is
accepted, after the original result/file integrity and all physical-input and
problem fingerprints pass. Admission returns a copy rebound to the current
handoff/result digests; snapshot import updates its file digest. Field values
and source ownership remain unchanged. Arbitrary diagnostic counters or other
metadata changes remain stale; an unavailable legacy match requires preparing
and rerunning the saved study. The historical handoff limitation string that
mentions nonlinear radiation is retained for metadata compatibility; the
thermal boundary contract above defines the supported ambient radiation law.

`tests/python/test_assembly_tetra_radiation.py` checks an exact combined-loss
slab on three meshes, pure radiation anchoring, zero emissivity, nonuniform
face fourth-power integration and its tangent, and a quadratic manufactured
source. The latter has centroid RMS errors 48.45, 12.88 and 3.273 K on 1, 2 and
4 subdivisions (more than threefold reduction per refinement). Invalid input,
bounded nonconvergence, saved roundtrip, legacy admission and corrupted heat
accounting are regression gates. Ambient values and convection coefficients
are prescribed inputs; no air momentum or energy PDE is solved.

Limits are 8 MiB per control/result record; handoff at most 100,000 cells and
vertices; thermal execution at most 5,000 cells and 10,000 nodes; bounded
geometry comparisons. The resident worker executes this bounded reference
kernel synchronously. It has no new per-operation cancellation, OS memory
quota or distributed backend; use process supervision for harder execution
limits. Large production thermal cases require another qualified backend.

## Radiation geometry and EM ports

`derive_assembly_view_factors` accepts explicitly oriented planar surface
triangles in metres and optional opaque occluder triangles. It computes each
pair's exchange area once, then uses `F_ij = H_ij / A_i` to preserve
`A_i F_ij = A_j F_ji`. Successive midpoint-subdivision quadrature levels are
change indicators, not rigorous error bounds for shadows. Unresolved view is
not ambient coupling; no rows are renormalized. The
[Howell C-11 opposed-rectangle reference](https://www.thermalradiation.net/sectionc/C-11.html)
supplies the analytical reference geometry. SPIKE's derivation, code, fixtures
and evaluated oracle are original; no external code or dataset was adapted.
View factors do not yet drive nonlinear radiosity or the new thermal solve.

EM/SI materials require explicit nonnegative `conductivity_s_m`, positive
`relative_permittivity` and `relative_permeability`, plus `id` and provenance.
Ports bind different signal and return exterior conductor faces and positive
`reference_impedance_ohm`. The handoff returns `executable: false` and
`ASSEMBLY_FIELD_BACKEND_UNAVAILABLE`: modal normalization and the general
retained-volume Maxwell/SI translator are not implemented. Harnesses,
connector mappings, rigid-flex links and bonds are retained in the assembly
identity and reported as unsupported connectivity, never silently substituted
with free-space isolation or ideal connections. Thermal execution rejects
those unresolved links as well.

## Worker and offline workflow

The JSON-lines worker supports five methods with fixed payloads:

- `prepare_assembly_field_handoff`: `{request}`.
- `run_assembly_field_thermal`: `{request, problem}`.
- `derive_assembly_view_factors`: `{request}`.
- `export_assembly_field_study`: `{request, problem, result?, include_results?}`.
- `import_assembly_field_study`: `{record, current_request?, current_problem?}`.

Unknown fields and executable overrides produce structured errors. Schemas
for handoff, thermal problem and view factors are in `schemas/`; numerical and
ownership constraints also require the semantic decoders.

`spike/assembly-field-study-file/v1` stores setup and nullable output with
canonical SHA-256 bindings. Exact integer/float spelling differences do not
change identity. Import checks result shape, nested experimental status, units,
counts, finite physical values, conservation reports and current setup identity.
Geometry, source/stack binding, placement, material or load changes require a
rerun. Hashes detect integrity/staleness, not authenticity or physical truth.
The assembly workspace provides **Assembly volume field study** in its analysis
section. Open a field-study JSON record, or paste a supplied conforming volume
request and problem in the advanced editor, then **Validate and apply volumes**.
The worker admits every physical occurrence before displaying imported results.
Thermal boundary values can be edited in the form; any edit immediately retires
the active result. **Run steady thermal** is enabled only for an admitted thermal
handoff without unresolved connectivity. EM/SI studies can be prepared and saved,
but cannot run a field solve through these controls.

**Save setup** and **Save with results** store the self-digested record at
`analyses.assembly_field_study` inside `.spike`. **Export setup** and
**Export with results** produce standalone JSON records that can be reopened
with **Open volume study**. Reset restores the admitted baseline, including its
result. Unapplied JSON cannot run or save; unsaved changes guard assembly edits.
Result presentation currently includes occurrence temperature extrema and
conservation/convergence/resource evidence; it does not add a spatial viewport
overlay. All numerical work remains in the resident worker.

Two native project methods bind reads and writes to an opened manifest:

- `read_assembly_field_study_in_project`: `{project_path, expected_manifest_payload_sha256}`.
- `save_assembly_field_study_in_project`: the same fields plus `{record}`.

Read returns the current canonical physical assembly, and `missing`, `current`
or `stale` state. A stale record never returns active output. Save requires exact
assembly identity and verified study integrity, preserves embedded members and
writes atomically. Setup-only saves recompute the file digest after removing
the result. Source/stack hashes remain caller declarations, as described above.

### Field workflow errors and recovery

Worker errors retain their structured SPIKE envelope and field-specific detail.
The GUI displays both and offers **Reload saved study** after a failed read.

| Detail | Resolution |
| --- | --- |
| `ASSEMBLY_FIELD_STALE` | Export volumes for the current occurrences, placement, references and layer stacks; review setup and rerun. Reopen an externally changed project to refresh its manifest. |
| `ASSEMBLY_FIELD_STUDY_DIGEST` or `ASSEMBLY_FIELD_RESULT_DIGEST` | Reopen the original intact record or regenerate it with the worker export method; do not edit a self-digested result by hand. |
| `ASSEMBLY_FIELD_CONNECTIVITY_UNSUPPORTED` | Supply an executable solver contract for every retained connection. These field methods cannot resolve connector/harness/bond topology; use an applicable reduced workflow meanwhile. |
| `ASSEMBLY_FIELD_BACKEND_UNAVAILABLE` | EM/SI port metadata are preparatory. The assembly Maxwell/SI execution path is pending. |
| `ASSEMBLY_FIELD_RESOURCE` | Refine the mesh scope within the documented budgets or split an independently valid study. Do not omit coupled physical occurrences to bypass coverage. |
| `ASSEMBLY_FIELD_BOUNDARY` or `ASSEMBLY_FIELD_CONTACT` | Review occurrence-scoped exterior face identities, matched contact geometry, area, conductance and retained contact definitions. |
| `SPIKE-FE-APP-E-0001` | Wait for the active heavy worker action to finish, then reload or retry. |

Run the [original guided example](../examples/assembly_field/README.md) and
the [validation record](validation/ASSEMBLY_FIELD_20261004.md). Knowledgeable
human numerical review, independent solver/measured correlation, arbitrary
CAD extraction, airflow, transient thermal and production release qualification
remain required.
