# Shape preservation and native compute implementation plan

Status: proposed work, inspected 2026-10-15. This document does not promote a
solver capability, add a dependency, or qualify a hardware backend. Current
authority remains [solver status](SOLVER_STATUS.md), [architecture](../ARCHITECTURE.md)
and [acceleration architecture](ACCELERATION_ARCHITECTURE.md).

## Existing foundations and gaps

| Area | Evidence in current source | Remaining work |
| --- | --- | --- |
| Board geometry | `project_geometry_index.py` generates design-bound Arrow tables; `project_geometry_artifacts.py` checks package manifest identity, member digests, schema and budgets | Canonical geometry tables are not a general CAD B-rep archive or solver mesh |
| Component CAD | `mcad_package_shape.py` extracts STEP topology through FreeCAD/OCC; `assembly_package_shapes.py` binds retained STEP, topology and transform digests | Its admitted state explicitly says `topology_ready: true`, `solver_ready: false`; topology numbering cannot be reused across arbitrary healing/reimport |
| Assembly exchange | `freecad_assembly_export.py` checks STEP reimport leaf count, placement, bounds and solid volume/count; a companion JSON carries SPIKE metadata | A complete save workflow must retain source shapes, occurrence identities and analysis selections, including missing/unsupported geometry diagnostics |
| Native kernels | CMake targets `spike_geometry`, `spike_peec`, `spike_peec_volume`, `spike_peec_volume_matrix`, `spike_thermal`, `spikes_core` use bounded C++ ownership; Eigen/OpenMP are existing dependencies | These targets do not collectively establish native execution of all PI, SI, thermal or EM workflows |
| Acceleration | `acceleration.py` serves hybrid DC: NumPy/Numba assembly, SciPy baseline, optional PETSc/MUMPS and CuPy/CUDA | No validated cross-vendor numerical OpenCL/OpenGL execution follows from WebGL rendering or GPU telemetry |

## Shape authority and saved project contract

Extend the existing project package and assembly artifact contracts. Do not
replace them with a second independent project database. Python owns admission,
identity and persistence; native CAD tools own topology operations; TypeScript
owns presentation; Rust remains the thin host.

Preserve three separately identified representations:

1. Retained source geometry: original STEP bytes and canonical board curves,
   contours, cutouts, stackup, copper thicknesses and via definitions. Preserve
   unsupported entities as reported source evidence instead of silently
   replacing them with boxes or coarse facets.
2. Derived CAD: an optional OCC B-rep cache and STEP assembly export bound to
   source/design digest, kernel/version, operation history and tolerances.
   A cache is regenerable and version-sensitive. STEP is interchange; the
   package's companion metadata remains electrical/material/selection authority.
3. Derived meshes: independently versioned surface, volume and preview meshes.
   A render tessellation cannot automatically serve as a physics mesh.

Each shape/occurrence record needs a stable SPIKE identity, parent occurrence,
source artifact digest, representation kind, local-to-parent transform, explicit
length unit, handedness, kernel/version and operation tolerance. Bind material,
net, layer, port and boundary assignments through SPIKE identities. Keep shared
part geometry separate from occurrence transforms. Transform or scale changes
invalidate dependent topology selections and meshes unless explicitly remapped.

Record CAD validation observations: body/shell/face counts, closedness,
orientation, bounding box, area and volume where defined, plus gaps, overlaps,
degeneracies and repairs. Healing is a recorded derived operation with before/
after invariants. Never silently fuse electrically distinct conductors. Define
unit and geometric comparison tolerances before roundtrip tests.

Save atomically using the existing bounded package writer. Verify every artifact
against its manifest, reject unsafe paths and oversized content, and retain
load/save compatibility. Original source loss must be visible. Save/open/save
tests must cover curved outlines, holes, transformed repeated parts, source
bytes, semantic IDs, stale digests and interrupted writes.

## Meshing and future MoM/BEM admission

Continue the optional Gmsh/OCC process boundary. Bind each mesh to geometry,
transform, material assignment, sizing policy, mesher/version and tolerance
digests. Export physical groups through explicit ID maps. Check element
orientation, non-manifold edges, disconnected regions, interface conformity,
minimum quality and volume/area agreement before solver admission.

A future surface MoM/BEM adapter additionally needs oriented surface regions,
material interfaces, conductor connectivity, ports, basis-function definitions,
singular/near-singular integration, boundary conditions and frequency conventions.
Open sheets can be valid for a particular formulation; closedness must be a
declared formulation requirement rather than a universal repair rule. Require
analytical references, mesh convergence, reciprocity and power balance as
applicable. CAD saving alone supplies none of that solver validation.

## Native library candidates and owners

These are integration candidates, not installed or benchmarked dependencies.
Profile representative workloads before choosing a backend. Keep independent
reference fixtures and the existing `AnalysisSpec`/`AnalysisResult` contracts.

| Workload | Existing owner and proposed boundary | Named candidates and limits |
| --- | --- | --- |
| 2.5D PI / hybrid DC | `hybrid_dc_solver.py` and `acceleration.py`; add a narrow C++ sparse bridge only after profiling | Eigen remains baseline; SuiteSparse CHOLMOD for admitted SPD systems, UMFPACK for general sparse systems; PETSc/MUMPS already has an optional orchestration route. None performs board extraction automatically |
| 3D PI / PEEC | `src/peec/` and existing retained-volume orchestration | Eigen/OpenMP for owned quadrature and matrix work; Ginkgo for suitable sparse iterative subproblems. Dense PEEC coupling needs separate compression/matrix-free validation; sparse libraries do not remove dense storage growth |
| SI | `si_channel.py`, `si_coupled_channel.py`, `si_network_workflow.py`; circuit execution in `src/spikes/` | Eigen for complex dense blocks; SuiteSparse KLU for suitable sparse circuit systems. SI remains in its current Python owner until a measured hotspot justifies a native kernel; library selection does not establish causal/passive channel extraction |
| Thermal | `src/thermal/thermal_solver.*`; retained tetrahedral orchestration in `assembly_tetra_thermal.py` | Eigen first; Ginkgo for iterative sparse systems; MFEM/libCEED as a larger optional FEM integration if justified. Preserve contacts, anisotropy and heat-balance oracles; legacy native fast-math/ISA flags need review before portable qualification |
| EM | `src/peec/` for bounded quasi-static kernels; `extensions/openems_suite/` and `extensions/palace_suite/` for external engines | MFEM/libCEED for a proposed native FEM route; PALACE/openEMS retain separate process ownership. None is an automatic MoM/BEM substitute; any new surface integral engine needs its own adapter and evidence |

Approve exact versions and license/redistribution obligations before integration.
SuiteSparse is a collection with component-specific terms. Optional executable
integration does not grant redistribution rights. No upstream source, examples
or fixtures were copied to create this plan.

## Cross-vendor compute policy

Use one worker capability catalog with backend, device, driver/runtime, supported
operations, precision, memory budget and qualification evidence. Runtime vendor
names alone never enable numerical execution. CPU remains a supported route.

| Backend | Applicability | Admission requirement |
| --- | --- | --- |
| OpenCL | Candidate Intel/AMD/NVIDIA devices with an installed implementation; Apple compatibility is deprecated | Probe exact operation and FP64 support, compile/run a bounded kernel and verify against CPU. Do not infer features from a version number |
| OpenGL compute | Optional specialized kernels where GL 4.3 or the compute extension exists | Separate numerical context/worker and precision checks; Three/WebGL rendering is not this API. Do not promise this path on Apple |
| Ginkgo CUDA/HIP/SYCL | Candidate NVIDIA/AMD/Intel sparse acceleration through supported builds | Check executor, selected solver/preconditioner, complex/real precision and installed runtime. This is not an OpenCL or Metal backend promise |
| Apple Metal | Possible separate future Apple execution adapter | Requires a concrete supported operation/precision implementation, reference checks, packaging and language-policy review. CPU fallback is the current defensible portable numerical route |

Automatic selection may fall back to CPU with recorded reasons; explicit device
requests fail clearly when unavailable. Validate physical residuals independently
of a backend's convergence flag. Include transfer, assembly, preconditioner,
solve and peak memory in benchmarks. Test failure, cancellation, insufficient
memory, non-finite outputs and stale cached factorizations. Never report a GPU
speedup from device discovery or mocked tests.

## Bounded next implementation

First deliver a shape-preservation save/open receipt over existing package
artifacts: retained STEP digest, canonical board geometry digest, occurrence
transforms, topology binding and explicit missing-geometry diagnostics. Use an
original curved-board/two-occurrence fixture and the existing FreeCAD roundtrip
checks. This closes an observable persistence contract without numerical changes.

Then implement capability-only OpenCL discovery behind the existing acceleration
catalog with `execution_supported: false` until one FP64 operation passes real
hardware and numerical gates. Choose the first accelerated operation from a
profile of hybrid DC; do not launch simultaneous solver rewrites. New execution
boundaries/dependencies require an ADR, dependency notices and targeted plus
mandatory project checks. Numerical release still requires knowledgeable human
review under CONTRIBUTING.md.

## Primary external references

References were checked 2026-10-15 for API selection only; no third-party source
code was used as implementation material.

- [Gmsh manual](https://gmsh.info/doc/texinfo/gmsh.html): OCC geometry, physical groups, meshing and runtime licensing.
- [Ginkgo executor documentation](https://ginkgo-project.github.io/ginkgo-generated-documentation/doc/master/group__Executor.html): OpenMP, CUDA, HIP and DPC++ executor families.
- [SuiteSparse UMFPACK guide](https://raw.githubusercontent.com/DrTimothyAldenDavis/SuiteSparse/master/UMFPACK/Doc/UMFPACK_UserGuide.pdf): sparse direct numerical library scope.
- [MFEM device documentation](https://docs.mfem.org/4.10/classmfem_1_1Device.html) and [libCEED setup](https://libceed.org/en/latest/gettingstarted/): build-dependent device execution.
- [Khronos shader requirements](https://wikis.khronos.org/opengl/Shader_Compilation): GL compute requires GL 4.3 or the relevant extension.
- [Apple OpenCL guidance](https://developer.apple.com/opencl/) and [Apple silicon porting](https://developer.apple.com/documentation/apple-silicon/porting-your-macos-apps-to-apple-silicon): deprecated compatibility and migration guidance.
