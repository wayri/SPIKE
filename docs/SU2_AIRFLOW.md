# SU2 cavity reference adapter

SPIKE can run a separately installed SU2 executable on an original generated
two-dimensional lid-driven square cavity and compare its velocity profiles with
the original SPIKE native cavity kernel. This is experimental reference work,
not assembly airflow, turbulence, fan modelling or conjugate heat transfer.
Knowledgeable numerical human review is required before release.

## Runtime and reproduction

Install the native serial/OpenMP SU2 executable from the
[official download portal](https://su2code.github.io/download.html). SU2 is a
separate LGPL-2.1 runtime; SPIKE bundles no SU2 source, binaries or examples.
Set `SPIKE_SU2_CFD` to the absolute `SU2_CFD` executable path, or set `SU2_RUN`
to its containing directory. PATH is also searched. For local development the
adapter additionally detects `artifacts/su2-runtime/v*/bin/**/SU2_CFD.exe`
(without the extension on POSIX).

From the repository root, using a Python environment with SPIKE dependencies:

```powershell
python scripts/build_native_airflow.py
python scripts/benchmark_su2_airflow.py --cells 16 32 64 --output artifacts/su2-benchmark
python -m unittest discover -s tests/python -p test_su2_airflow.py -v
```

`--su2-executable` and `--native-executable` are trusted local CLI overrides.
The worker's request JSON cannot select executables, mesh files, configuration
text or output paths. The comparison writes `comparison.json`, both solvers'
full field results, and SU2 input mesh/config, history and stdout/stderr files.
Fresh per-run directories prevent reuse of stale output. Results are retained
for audit; they are not automatically removed.

## Contract and physical case

`python/spike_core/su2_airflow.py` exposes `su2_airflow_capabilities()` and
`run_su2_airflow(request)`. Allowed request fields are `case` (only
`lid_driven_cavity`), `cells` (even 8..128, default 32), `reynolds` (1..400,
default 100), `iterations` (10..100000, default 10000), and `timeout_s`
(1..1800, default 300). Unknown fields and non-finite values are rejected.

The square has side length 1 m, constant density 1 kg/m^3, lid velocity
(1, 0) m/s and dynamic viscosity `1/Re` Pa s. The remaining walls are stationary
and no slip. Energy and turbulence are disabled. Thus velocity values are also
velocities normalized by lid speed, while pressure is in Pa and is meaningful
only up to an additive constant in this closed domain.

The mesh generator independently enumerates Cartesian nodes and positive
counterclockwise quadrilaterals. SU2 uses an incompressible finite-volume
formulation with FDS convection, MUSCL reconstruction without limiting,
Green-Gauss gradients and implicit pseudo-time stepping. Both meshes refine
the same physical domain, but the native solver stores staggered/cell-centered
quantities and SU2 returns nodal quantities. These are distinct discretizations.

The parser checks finite values, exact node coverage, unique IDs and agreement
with the generated coordinates. `completed` requires all final RMS pressure,
x-velocity and y-velocity base-10 residuals to be at most -9. Otherwise a
successfully executed solve is `failed_to_converge`. Process exit alone never
establishes convergence. Partial or malformed fields are rejected.

## Process limits and provenance

Execution reuses SPIKE's bounded `sparselizard_process.run_adapter_process`
boundary: no shell, one OpenMP thread, 2 GiB process memory limit, bounded
stdout/stderr, cancellation and timeout termination, and Windows Job Object or
POSIX process-group containment. POSIX additionally imposes a file-size limit;
on Windows result files are size-checked when admitted. This adapter is not
a sandbox for untrusted executable code. SU2 must be installed by a trusted
host/user. Native OpenMP binaries are supported; MPI launch is not implemented.

The returned result records the release banner, executable SHA-256, mesh,
configuration, solution and history SHA-256, elapsed time and retained run
directory. A cancellation callback can be supplied by trusted Python callers.
Unavailable runtime, malformed outputs, cancellation and failed launches raise
explicit exceptions. Timeout/cancellation do not return partial physics.

## Comparison and acceptance

The benchmark runs Re=100 on 16, 32 and 64 cells per direction by default.
It linearly interpolates each solver's centerlines to the same 19 locations
0.05, 0.10, ..., 0.95: horizontal velocity at x=0.5 and vertical velocity at
y=0.5. Sampling avoids the discontinuous moving-lid corner data. It records
maximum absolute and RMS differences normalized by lid speed, convergence
diagnostics and successive-grid profile changes for each solver.

The declared comparison criterion is converged runs, decreasing maximum
cross-solver difference for each velocity component on refinement, and a finest
grid maximum difference no larger than 0.03 times lid speed. The script returns
nonzero if these criteria fail or cannot be evaluated. This is a bounded
cross-code acceptance criterion, not an assertion of continuum accuracy.
Independent analytical invariants and the native kernel's conservation tests
remain necessary. Pressure is recorded but not compared because its arbitrary
gauge and near-corner behaviour need a separately defined metric.

Actual runtime evidence on 2026-10-11: the official Windows OpenMP SU2 8.5.0
binary ran the independently generated 16-cell cavity and converged in 328
history rows. Final log10 residuals were pressure -10.18591624, u -9.015766388,
v -9.037032531. This individual run alone does not establish cross-code agreement;
the generated comparison report is authoritative for the full refinement run.

The downloaded archive was
`https://github.com/su2code/SU2/releases/download/v8.5.0/SU2-v8.5.0-win64-omp.zip`
(28,043,921 bytes), SHA-256
`4466fe21aedb5e0bad57afd45f829acbdec6ec79fe8c3f8954ddea06a4b4bc11`.
The tested `SU2_CFD.exe` SHA-256 was
`3cb60646b31c08e468441be9f3497601960d4bb31349e6329982bcdeed599248`.
Archive hashes record local provenance, not an upstream signature guarantee.

## Public interface references and clean-room statement

Only public interface documentation and binary release metadata informed this
adapter. No external implementation, mesh generator, downloaded example or
testcase was used as source material. The Cartesian indexing, case choices,
configuration authoring, CSV admission, synthetic test oracles and comparison
logic were independently authored for SPIKE. Search engines may surface
upstream source/example snippets; those were not used as implementation input.

- [Mesh file specification](https://su2code.github.io/docs_v7/Mesh-File/):
  dimensionality, zero-based nodes, VTK quadrilateral identifier and markers.
- [Physical definition](https://su2code.github.io/docs_v7/Physical-Definition/):
  incompressible density, velocity, dimensionalization and viscosity interfaces.
- [Version 7 guide](https://su2code.github.io/docs_v7/Guide-to-v7/):
  moving-wall surface options and convergence fields.
- [History and solution output](https://su2code.github.io/docs_v7/Custom-Output/):
  ASCII restart output and residual history interface.
- [Execution](https://su2code.github.io/docs_v7/Execution/): native executable
  and thread-count command-line interface.

Synthetic tests verify area/orientation/closed boundaries, exact linear
centerline interpolation, incomplete/duplicate/non-finite/coordinate-invalid
field rejection, residual convergence admission, runtime absence and
cancellation before launch. They do not pretend to be external solver evidence.
