# Experimental native laminar CFD foundation

SPIKE owns a standalone C++ square-cavity momentum kernel in `src/airflow`.
Python `native_airflow.py` owns admission, units, process timeout, provenance and
results. This is a bounded numerical foundation for comparison with a separately
installed SU2 runtime. It does not solve imported geometry, 3D flow, energy,
buoyancy, turbulence, fans, solid conduction or conjugate heat transfer.
Knowledgeable human numerical review is required before release.

## Reproduction

```powershell
python scripts/build_native_airflow.py --generator "Visual Studio 18 2026"
$env:PYTHONPATH = "python"
python -m unittest discover -s tests/python -p test_native_airflow.py -v
python -c "from spike_core.native_airflow import run_native_cavity; print(run_native_cavity({'n':32})['diagnostics'])"
```

On other systems omit the generator or supply an installed CMake generator.
The kernel requires only a C++20 compiler and standard library. CMake builds
`spike_native_airflow` and runs native numerical tests. Python discovers the
executable in `build-native-airflow[/Release]`, or the locally configured
`SPIKE_NATIVE_AIRFLOW_EXECUTABLE`. Worker requests cannot supply executables.
Packaged workers include the built executable in their PyInstaller `native`
directory and discover it there without a source checkout. Build the native
CFD target before `scripts/build_packaged_worker.py`; worker packaging fails
if the executable is absent. The packaging gate also checks discovery inside
the artifact and executes an eight-cell cavity through the frozen worker.
The environment override also applies to packaged
workers. Executables are local trusted software. The environment override is not a
sandbox for untrusted code. The adapter terminates the direct process on a
300-second timeout. No child processes are launched by this kernel.

## Contract and dimensional quantities

`run_native_airflow(request)` accepts only these keys:

| Key | Default | Admitted values |
| --- | --- | --- |
| n | 32 | Even integer, 8 through 128 |
| reynolds | 100 | 1 through 400 |
| max_steps | 100000 | Integer, 1 through 200000 |
| steady_tolerance | 1e-7 | 1e-10 through 1e-3 |
| length_m | 1 | Positive, 1e-9 through 1e9 |
| lid_velocity_m_s | 1 | Positive, 1e-9 through 1e9 |
| density_kg_m3 | 1 | Positive, 1e-9 through 1e9 |

The admitted range is a software bound, not accuracy qualification throughout
that range. The benchmark target is Re=100. Coordinates increase right/up;
the top wall moves right, all other walls are stationary and impermeable.
At lid endpoints the stationary side-wall normal velocity takes precedence.
The discontinuous corner boundary limits smooth-solution spatial accuracy.

The kernel uses x/L, t U/L, velocity/U, pressure/(rho U^2). Dynamic viscosity
is derived as rho U L/Re. Returned arrays `x_m`, `y_m`, `u_m_s`, `v_m_s`,
`pressure_pa` contain cell-centred values, row-major from bottom left.
Pressure has zero arithmetic mean, with no absolute pressure interpretation.
Centerlines contain dimensionless u/U at x/L=.5 and v/U at y/L=.5, sampled
at .05 through .95 in .05 increments by linear cell-centred interpolation.
On the coarsest grid a requested point can lie between the first/last centre
and a wall; interpolation there includes the prescribed wall value.
Diagnostics `time`, `dt`, `steady_rate_linf`, `divergence_linf` and pressure
equation residual are dimensionless. `diagnostic_units` records their reference
scales, and `dimensional_diagnostics` separately returns SI time, timestep,
divergence and velocity-change rate. Velocity convergence rate has scale U^2/L;
divergence has scale U/L. Pressure-equation residual is for the dimensionless
negative-Laplacian correction equation.

`converged` means ten successive steps below the requested maximum velocity
change divided by dt, with divergence below 1e-7. It does not mean externally
validated. An exhausted step budget returns `failed_to_converge` and no fields.
Nonfinite state, incompatible mass flux, failed pressure solve, malformed output,
unsupported input or process failure raises an error. No partial field is
admitted as an accepted result. Result provenance includes the executable SHA256
and the canonical request SHA256. `production_qualified` is always false.

## Independently derived discretization

The starting balance laws are div u=0 and du/dt=-div(u tensor u)-grad p+
(1/Re) Laplacian u. A uniform staggered MAC layout places pressure at cell
centres, u at vertical faces and v at horizontal faces. Integrating each
momentum balance over its face-centred control volume gives differences of
fluxes at opposite faces divided by h. Face fluxes use arithmetic averages:
the u east/west normal flux is ((u_i+u_neighbor)/2)^2; the cross flux is the
product of the two adjacent u and v averages at the control-volume corner.
The v equation follows the same integral balance with its own faces. Shared
internal fluxes cancel pairwise, making the momentum transport conservative.
Second differences approximate diffusion. Odd-reflected ghost tangential
velocities impose no slip; top ghosts are 2 U_lid-u_inside.

Explicit Euler predicts u_star using current pressure, convection and viscosity.
With D the cell flux divergence and G the face pressure gradient, solve

```
(-D G) phi = -D u_star / dt
u_next = u_star - dt G phi
p_next = p + phi
```

These equations imply D u_next=0 up to dt times the pressure solve residual.
Zero normal wall corrections give homogeneous Neumann pressure-correction
boundaries. The pressure matrix has one constant null mode. The solver rejects
a material RHS mean, removes roundoff mean, uses conjugate gradients on the
zero-mean subspace and recomputes the actual infinity-norm residual before
acceptance. Adding the correction to current pressure makes this an incremental
projection; at a steady fixed point phi tends to zero and the discrete momentum
balance retains the accumulated pressure gradient.

The time step is min(.15 h^2/nu, .2 h/max(1,|u|,|v|)), where stored ghosts are
included in the maximum. The diffusion coefficient stays below the explicit
2D stability limit 1/4. Centered convection has no numerical upwind dissipation;
the bounded Reynolds range and selected grid still need convergence evidence.
CG conditioning worsens approximately as n^2; work and memory are bounded by
grid and iteration caps. Resident numerical arrays scale as O(n^2); the maximum
grid has 16384 cells. The native process writes one bounded final JSON payload.
Python's four-million-character output admission limit is checked after process
completion; it is not an allocation limit on subprocess capture. The bound
relies on the trusted native executable's fixed output shape and grid cap.

## Original verification oracles and limitations

All implementation, prose and fixtures here were independently authored from
the balance equations above. No external implementation, example mesh, cavity
reference table or external test data was inspected, copied or adapted. The
derivation above is the method provenance for this original implementation.

For q=cos(pi x) cos(2 pi y), homogeneous Neumann walls are exact and
-Laplacian q=5 pi^2 q. The discrete cosine sampled at centres is an exact
eigenvector with eigenvalue 4 n^2 [sin^2(pi/(2n))+sin^2(pi/n)]. The native test
independently uses these expressions to check the operator's second-order
refinement and pressure solve at n=8,16,32,64. Other native assertions check
incompatible forcing rejection, exact rest preservation, unaccepted truncated
fields, divergence and decreasing Re100 cavity centre-velocity changes on
16/32/64 grids. Python tests check strict admission, malformed output, timeout,
real executable convergence and independent dimensional scaling.

These tests establish the stated operator, process and refinement invariants;
they are not a full Navier-Stokes manufactured-solution qualification. The
cavity lacks a smooth closed-form solution. Agreement with an independent SU2
run and convergence of both discretizations must be reported with actual engine
version, settings, tolerances and grids. Neither successful compilation nor a
refinement trend alone establishes CFD accuracy. Pressure near lid corners,
wall stresses, transients and higher-Re flow remain unqualified.

## Recorded native evidence, 2026-10-11

CMake with Visual Studio 18 2026 / MSVC 19.51.36256.0 built the native target.
The native CTest passed in 82.88 seconds. The pressure operator infinity-norm
errors against the continuous cosine oracle were 1.9158, 0.523566, 0.133787
and 0.0336294 for n=8,16,32,64. Successive error ratios approach four.
The pressure solves' actual residuals were at most 5.08e-12 for that oracle.

| Re100 grid | Steps | Centre u/U | Maximum divergence | Final velocity-change rate |
| --- | --- | --- | --- | --- |
| 16 x 16 | 4240 | -0.188631 | 3.393e-12 | 9.676e-8 |
| 32 x 32 | 8441 | -0.203650 | 2.646e-12 | 9.841e-8 |
| 64 x 64 | 16858 | -0.207783 | 1.495e-12 | 9.923e-8 |

All table quantities except step/grid counts are dimensionless. The centre
velocity changes decrease from approximately 0.0150 to 0.00413. This is
self-refinement evidence, not an independent cavity accuracy measurement.
The six Python boundary tests passed, including actual native execution,
dimensional rescaling, forged diagnostic rejection, nonfinite-field rejection,
wall-aware coarse-grid interpolation and process timeout behavior.

## Packaged runtime verification, 2026-10-16

`python scripts/build_native_airflow.py --generator "Visual Studio 18 2026"`
rebuilt the kernel; its native CTest passed in 77.77 seconds. All seven adapter
contract tests passed under the release Python 3.12.9 environment.
`.venv/Scripts/python.exe scripts/build_packaged_worker.py --keep-work` completed
its frozen worker qualification and integrity manifest. With no
`SPIKE_NATIVE_AIRFLOW_EXECUTABLE` override and the artifact directory as working
directory, `cfd_capabilities` discovered `_internal/native/spike_native_airflow.exe`
and `run_native_cfd` at n=16, Re=100 converged in 4240 steps. The maximum
dimensionless divergence was 3.393e-12 and final velocity-change rate 9.676e-8.
The artifact includes the MSVC runtime DLLs collected by PyInstaller. This is
local packaging/execution evidence; clean-machine installation, upgrade and
uninstall qualification remain release gates. The model limits above still apply.

## Desktop workbench

Open Menu, search `native CFD`, and choose **Native CFD cavity benchmark**
under Design & view > Workspace panels. Universal search also exposes it when
an operational local worker is available. Select **Check / retry runtime**,
choose the grid and Reynolds number, then **Run native CFD**. Execution uses
the worker process; returned converged velocity magnitude and gauge pressure
are available as interactive heatmaps. Changed inputs mark prior results stale.
Unavailable runtimes, failed convergence and malformed fields have explicit
recovery states. This is the bounded cavity model described above; it does not
accept board geometry or provide conjugate heat transfer.

The integrated production frontend build, payload admission tests, viewport
cadence/vector tests and architecture/control checks passed on 2026-10-16.
Browser preview verified menu discovery and the unavailable-worker layout.
Native window screenshot acceptance was blocked by the computer-use helper's
failure to activate the development host dialog. Installed and published Gamma
binaries were not replaced by this verification.
