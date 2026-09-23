# Advanced systems laboratory — engineering examples, not product designs

## Interactive two-wheeler: `two_wheeler_dashboard.spksch`

Open the file through **File → Open** (not netlist import, which loses dashboard
and controller setup). Go to Controller, review the C code and assumptions, approve
trusted execution, Compile, enable attachment to Continuous, then Run closed loop.
In Dashboard choose Run mode, select Throttle, enter 0.2 and Send. Brake commands
0..1 override throttle and request negative current, tapered near zero speed.
Pause/resume and stop use the normal simulation controls. Controller execution is
a subprocess per 1 ms virtual tick; wall-clock operation may be much slower than
real time. A working C compiler is required. Never attach this example to hardware.

The native electrical plant includes armature R/L and a 1 mΩ current shunt. The C
block integrates J*domega/dt=kt*I-B*omega and drives back-EMF using an independent
voltage source. V(omega) represents motor rad/s; reflected inertia is 0.30 kg m²,
viscous damping is 0.02 N m s/rad, and kt=ke=0.12 in SI. Mechanical integration is
explicit sampled Euler, not a native coupled DAE. With no attached controller the
plant is stationary and there is no closed-loop behavior.
The hypothetical vehicle mapping is 0.25 m wheel radius and 6:1 reduction; speed in
km/h is omega*0.15. This is an averaged DC-equivalent drive, not a BLDC/PMSM phase
simulation. Armature current is not a measured three-phase motor current.

The sampled PI current loop has anti-windup, 12-bit ADC quantization, voltage limiting,
brake priority and illustrative thermal foldback. The temperature is a conduction-only
RC estimate: Ploss=0.015 I² W, Rtheta=1 K/W, Ctheta=100 J/K, ambient=25°C. It is not
semiconductor junction temperature or a validated safe operating area calculation.
Bus voltage is a 72 V minus 0.03 I estimate; it limits controller output but is not
a charge-conserving battery chemistry/SOC model. Regen energy absorption is idealized.
No SOC/full-battery inhibit, friction brake, reverse interlock or independent safety
shutdown has been validated. Use negative armature current as the regen indicator.

Approximate unsaturated current-loop design with back-EMF feedforward:
plant G=1/(0.0005 s+0.08), PI=(0.4 s+40)/s. Closed-loop characteristic is
0.0005 s²+0.48 s+40, with poles approximately -92.2 and -867.8 rad/s and reference
transfer zero -100 rad/s. These are continuous-time design calculations, not poles
of the full sampled, saturated electro-mechanical system. ADC quantization and
voltage/thermal limits invalidate that local linearization.

## Switching stress: `gate_miller_ringing.cir`

Run the native transient and probe V(gate), V(drain), V(command), I(Lpackage).
This is a separate nanosecond-scale linear RLC/capacitive-injection experiment.
It shows gate-loop resonance and drain-to-gate coupling through a fixed 100 pF Cgd.
It does NOT model a nonlinear Miller plateau, voltage-dependent Cgd, channel turn-on,
avalanche, reverse recovery, shoot-through or a manufacturer MOSFET. Do not interpret
these traces as stress predictions for the averaged EV example.

## Fault injection: `redundant_sensor_fault.cir`

Probe V(a), V(b), V(filtered_a)-V(filtered_b), V(watchdog). Channel B sticks high at 31 ms.
Two RC sensor channels and a discrepancy filter expose the fault. The heartbeat
filter demonstrates timing only; no certified fault detector or shutdown is implied.
This is useful for teaching safety-monitor concepts, not a life-critical design.
There is no claimed IEC 61508, ISO 26262 or medical-device compliance.

## Coverage and limits

These examples separate slow vehicle dynamics from fast switching parasitics instead
of synthesizing gate ringing onto unrelated dashboard signals. Full inverter phases,
FOC, nonlinear WBG models, battery chemistry, degradation, coupled thermal meshes,
hardware interaction and complete mixed-signal timing remain future integration work.
All component/controller parameters are explicit hypothetical values, not measurements.
The generator script recreates the dashboard from the checked-in deck and C source.
Future installers bundle this folder; an already installed beta.5 does not auto-update.

## Verification

`scripts/verify_ev_closed_loop.py --library <native-library> --output <report.json>`
compiles this exact C controller, connects it to the native interactive circuit,
applies 30% throttle, verifies positive current/acceleration, applies full braking,
and verifies negative current after another 120 ms virtual time. It records the
actual retained result, not generated decorative traces. This short smoke check
does not establish long-duration stability or vehicle/control-system qualification.
