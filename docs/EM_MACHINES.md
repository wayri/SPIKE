# EM machines and electromagnets

## Source workbench

Open **EM > Machines** or **Machines and electromagnets** in the EM setup dock.
No PCB is required. Enter explicit SI parameters and run the desktop worker.

- PM DC motor: applied voltage, rotor inertia, winding R/L, reciprocal torque
  and back-EMF coefficient, applied shaft torque and viscous damping.
- PM DC generator: the same rotor dynamics with an explicit resistive load.
- Electromagnet: one linear magnetic path and uniform gap; flux, inductance,
  core/gap flux density, gap-closing force, energy and copper loss.

Plots use shared zoom, pan, axis and export controls. Setup and latest result
are retained in the project EM setup; changing a parameter clears the old result.
Export setup/result JSON independently. Browser previews cannot run the worker.

## Signs, equations and units

Positive current enters the machine. Positive external shaft torque drives
positive rotation. Negative terminal electrical power indicates generation.
Reciprocal K uses N m/A = V s/rad; do not enter a V/krpm value.

For a motor, L di/dt = V - R i - K omega,
J d omega/dt = K i + torque_external - b omega, and d theta/dt = omega.
Generator mode has V_terminal = -R_load i and includes R_load in electrical
dynamics, with load dissipation separate from winding losses.

Implicit midpoint in energy-scaled coordinates preserves discrete power balance.
Energy uses midpoint quadrature, not displayed endpoint power trapezoids.
Energy closure alone does not establish accuracy: halve the time step and compare.

Electromagnet reluctance is core_length/(mu0 mu_r core_area) +
gap/(mu0 gap_area). Flux = N I/reluctance; inductance = N²/reluctance.
Gap-closing force = flux²/(2 mu0 gap_area).
Linear energy/coenergy = L I²/2. Core dimensions stay fixed when differentiating
the single gap. Declared engineering mu0 approximation: 4 pi times 1e-7 H/m.

## Reproduce examples

From the repository root with the project Python environment:

~~~powershell
.venv/Scripts/python.exe -m python.spike_core.cli --output output/em-machines/motor.json em-machine --request examples/em_machines/motor.json
.venv/Scripts/python.exe -m python.spike_core.cli --output output/em-machines/generator.json em-machine --request examples/em_machines/generator.json
.venv/Scripts/python.exe -m python.spike_core.cli --output output/em-machines/electromagnet.json em-machine --request examples/em_machines/electromagnet.json
~~~

Worker: run_em_machine with exactly one request object. Unknown fields,
non-finite values, invalid ranges, fractional turns and more than 20,000 steps
are rejected. Results retain input SHA-256, sign conventions and validity limits.

Independent checks cover physical-coordinate matrix exponential comparison,
step halving, RL and acceleration oracles, lossless conservation, generator
sign/load heating, Maxwell gap pressure and a finite-difference coenergy derivative.
The implementation, derivation and fixtures are independently authored.

## Limits and detailed PM field target

The separate [geometry-based machine and actuator study](MAGNETIC_MACHINE_STUDIES.md)
now provides experimental planar nonlinear FEM, Maxwell-stress force/torque,
quasi-static motion and stationary eddy/thermal coupling. Its limits and
validation differ from the parameter models described above.

The parameter models themselves do not solve 2D/3D magnetic FEM or viewport fields.
Induction machines, nonlinear B-H curves, saturation/hysteresis, eddy/core losses,
commutation/inverters, thermal feedback, torque ripple and rotating STEP solids
remain unsupported. Numerical human review is required before release.

The first detailed field target is PM motor/generator analysis. This requires
reviewed rotor/stator/magnet geometry, magnetization, winding/drive data, steel
B-H curves, conductivity, moving-interface air-gap meshing and reference
torque/back-EMF/energy plus mesh/time convergence checks. Existing Elmer discovery
does not provide an executable machine adapter.
