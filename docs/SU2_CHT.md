# SU2 fluid-solid heat-transfer reference

The SU2 CHT adapter executes an independently generated three-zone problem using
the installed SU2 runtime. It returns solved fluid velocity and temperature,
solid temperature, interface temperatures and conductive heat-balance checks.
It is experimental and limited to a planar cavity between hot and cold slabs. It does
not admit assembly CAD, boards, fans, turbulence, radiation, buoyancy, contact
resistance or temperature-dependent properties.

## Run and inspect

Install/configure SU2 as described in [SU2 airflow](SU2_AIRFLOW.md). From the
repository root with the SPIKE Python environment:

```powershell
python scripts/benchmark_su2_cht.py --cells 16 32 64
python -m unittest discover -s tests/python -p test_su2_cht.py -v
```

The benchmark retains `artifacts/su2-cht-three-zone-benchmark/comparison.json`, six full
result JSONs and all generated SU2 meshes, configurations and solver output.
The benchmark allows 900 seconds per case by default (`--timeout-s`, maximum
1800); the worker default remains 300 seconds. A 64-cell stationary case can
exceed the worker default on a busy machine. After interruption, `--resume`
reuses a saved case only after verifying the current compiled inputs, runtime
identity and retained output hashes, then re-admitting its fields and checks.
`--output` changes that local destination; `--su2-executable` is a trusted CLI
override. These paths and raw configuration text are not accepted through
worker request JSON. Unavailable engines, failed processes, incomplete fields
and incorrect node identities produce explicit failures. Unconverged solves
remain `failed_to_converge` and must not be displayed as completed studies.
Converged solves violating the temperature-boundary or passive-range checks
are `failed_validation`; their fields remain audit evidence, not accepted results.

## Request and result

`su2_cht_capabilities()`, `prepare_su2_cht(request)` and
`run_su2_cht(request)` are the public Python entry points. Preparation returns
the exact fixed geometry, material and boundary choices without executing SU2.
The request admits only `cells` (multiple of four, 8..64, default 16),
`lid_speed` (0..1 m/s, default 1), `outer_iterations` (10..20000, default 5000)
and `timeout_s` (1..1800, default 300).

The result contract is `spike/su2-cht-result/v1`. `zones.fluid` contains
row-major nodal `x_m`, `y_m`, `temperature_k`, `u_m_s` and `v_m_s` arrays.
`zones.solid` (hot) and `zones.cold_solid` contain `x_m`, `y_m` and
`temperature_k`. `interface` (hot) and `cold_interface` contain
the corresponding x locations, both temperatures and both upward conductive
flux estimates. `diagnostics` records heat rates per metre of out-of-plane
depth (W/m), temperature jump (K), and dimensionless relative balance errors.
`convergence` retains the final log10 block-coupling residuals and history count.
`provenance` retains executable/input/output hashes, SU2 version, time and run
directory. No physical values are inferred from engine availability.

## Independently defined physical problem

The fluid occupies 0 <= x <= 1 m, 0 <= y <= 1 m. The hot solid occupies
0 <= x <= 1 m, -0.25 <= y <= 0 m; the cold solid occupies
0 <= x <= 1 m, 1 <= y <= 1.25 m. Matched conforming interfaces at y=0 and y=1
enforce temperature and normal heat-flux continuity. The bottom of the hot slab
is held at 310 K and the top of the cold slab at 300 K. The fluid lid moves in
+x; its temperature is solved at the cold CHT interface, not prescribed. The lateral
walls are stationary and adiabatic. There is no mass flow through the enclosure.

Reference material values are deliberately simple: all densities are
1 kg/m^3 and all specific heats are 1 J/(kg K). Fluid dynamic viscosity is
0.01 Pa s and conductivity is 0.01 W/(m K); solid conductivity is
0.1 W/(m K) for both slabs. These are a numerical reference fluid and solid, not a claim of
ordinary air and aluminium properties. A 1 m/s lid gives Re=100 and Pe=100.
Zero lid speed supplies the conduction oracle.

The fluid solves constant-density incompressible Navier-Stokes with its energy
equation enabled. The solid solves SU2's finite-volume `HEAT_EQUATION`.
Temperature/Robin heat-flux coupling is iterated between the zones. The generated
mesh has n by n fluid cells and n by n/4 cells in each solid. All use square cells.
The wall motion is an idealized prescribed tangential fluid boundary condition:
the solid heat equations contain conduction but no material advection or
mechanical/tribological model of a moving lid. This reference does not model
a physically translating finite solid slab.

## Units and acceptance evidence

SU2 8.5 stores fluid enthalpy in its restart solution. This adapter does not
assume that enthalpy equals absolute temperature: it reads the explicitly
exported `Temperature` field in ASCII VTK and checks that its coordinates match
the high-precision restart mesh. Solid restart temperature normalization is
made explicit by setting its reference freestream temperature to 1 K. The
parser independently requires the hot boundary to equal 310 K, rejecting a
mis-scaled solid field. ASCII VTK has limited printed precision; near 300 K,
rounding is about 0.00005 K and affects gradient estimates at fine resolution.

Convergence requires all six coupled log10 residuals (fluid pressure, two
velocities, fluid enthalpy and both solid temperatures) <= -9. This avoids accepting
a converged flow with unconverged thermal coupling. Relative heat balances are
computed independently from one-sided Fourier gradients and trapezoidal
integration. They are discrete checks with a first-order boundary-gradient
error, not exact SU2 face-flux exports or an estimate of continuum error.

For the stationary fluid, integrating Fourier's law through three layers yields
the series resistance R = 2(0.25/0.1) + 1/0.01 = 105 m^2 K/W. Thus q =
10/105 = 0.0952380952380952 W/m^2. The hot solid temperature is
310 - q(y+0.25)/0.1, the cold solid temperature is 300 + q(1.25-y)/0.1,
and the fluid temperature is 300 + q(0.25/0.1 + (1-y)/0.01).
This derivation is the independent analytical oracle, without external test data.

The benchmark requires convergence, conduction error below 0.001 K and 0.1%
heat-rate error, interface temperature jump below 0.001 K, interface heat-rate
mismatch below 0.1%, and global balance mismatch below 2%. The finest moving-flow
heat-rate change must be below 10% on refinement. Thresholds are reported in
the JSON before execution. Moving cases also require a maximum fluid speed
above 0.5 m/s and heat transfer at least 1.2 times the same-grid zero-speed case,
so stationary conduction cannot be mistaken for executed convective transport.
Failure exits nonzero. These checks do not qualify
general conjugate heat transfer or hardware temperatures. Knowledgeable human
numerical review is required before release.

Additional mandatory admission checks require the prescribed cold solid boundary to be
within 0.0001 K of 300 K and the passive temperature field within 0.001 K of
300..310 K. These are independent of the iterative residual convergence test.

### Actual three-zone SU2 8.5.0 evidence, 2026-10-11

The 16-to-32-cell benchmark passed all declared checks, for both zero-speed
conduction and 1 m/s moving flow. The analytical maximum temperature error was
0.00004762 K and relative heat-input error was at most 1.24e-8. Moving-flow heat
input increased from 0.18540798 to 0.19951747 W/m on refinement (7.0718% change),
and was respectively 1.9468 and 2.0949 times the same-grid conduction heat rate.
Maximum fluid speed was 1 m/s in both moving cases. Global heat-balance mismatch
decreased from 0.31781% to 0.05853%. Both interface temperature jumps remained
below 0.00005 K and both interface flux mismatches below 0.0013%. The prescribed
solid temperature errors were below 7e-12 K; all temperatures remained 300..310 K.

The earlier 64-cell three-zone stationary run hit its 300-second execution
limit without publishing a result. Its incomplete artifacts are retained but
are not passed evidence. The accepted four-case report is
`artifacts/su2-cht-three-zone-benchmark/comparison.json` (`passed: true`).
Reproduce that accepted scope with `--cells 16 32`; the benchmark's default
16/32/64 scope now permits 900 seconds per case but has not been fully rerun.
Two-grid refinement is a bounded consistency check, not asymptotic mesh
independence or hardware-temperature qualification.

### Preserved earlier two-zone failure, 2026-10-11

The earlier two-zone model imposed 300 K directly on the moving fluid boundary
and had no cold slab. Its saved data remain in `artifacts/su2-cht-benchmark/`;
these files describe a different physical problem and are not overwritten or
reinterpreted as three-zone results.

All six 16/32/64-grid runs converged iteratively. The three zero-speed cases
passed analytical and boundary admission, with maximum temperature error
0.0000488 K and maximum relative heat-input error 4.75e-8. The finest stationary
case required 1651 outer coupling iterations. Limited ASCII temperature precision
accounts for a finest-grid estimated heat-balance difference of about 0.026%.

The moving-flow cases did **not** pass validation: cold-boundary maximum errors
were 0.0469, 0.0173 and 0.0063 K at n=16,32,64. Their minimum fluid temperatures
were 299.9730, 299.9864 and 299.9937 K. These errors decrease with refinement
but exceed the declared boundary and passive-range criteria. Their interface
temperature jumps stayed below 0.00005 K and global heat-balance differences
decreased from 0.294% to 0.00734%; those checks cannot override the failed
temperature-boundary checks. The saved benchmark is therefore `passed: false`.

Two targeted runtime experiments did not resolve this discrepancy: scaling
heat capacities and conductivities together preserved it, and driving a
different wall while keeping the cold wall stationary did not remove it.
The cause of that boundary discrepancy remains unresolved without further
supported-interface investigation or an upstream issue. SPIKE does not label
those moving cases validated, suppress the offending temperatures, or replace
them with prescribed values. The current three-zone problem places both fixed
temperatures on solid boundaries and explicitly resolves heat conduction through
the added cold slab; this is a different physical case with the same strict
temperature tolerance, not a relaxed acceptance rule.

## Method and implementation provenance

Public SU2 interface documentation informed option names and file syntax:
[multizone](https://su2code.github.io/docs_v7/Multizone/),
[CHT interface description](https://su2code.github.io/tutorials/Static_CHT/),
[boundary conditions](https://su2code.github.io/docs_v7/Markers-and-BC/), and
[output fields](https://su2code.github.io/docs_v7/Custom-Output/).
The installed executable's dry-run output confirmed actual supported field
names; runtime diagnostics corrected obsolete documentation identifiers.
No upstream source, mesh, downloadable configuration, testcase or reference
dataset was copied, translated or adapted. Search results may surface source
snippets, which were not implementation material. Geometry, compiler, parser,
tests, balance derivation and benchmark choices are original SPIKE work.

SU2 remains separately installed and LGPL licensed. The original Apache-2.0
adapter reuses SPIKE's existing bounded process boundary and runtime detection;
see [runtime provenance and limits](SU2_AIRFLOW.md). Both input and executable
hashes are checked before and after execution. Cancellation and timeouts do
not publish partial successful results.
