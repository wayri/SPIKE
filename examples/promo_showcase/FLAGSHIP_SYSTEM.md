# Flagship: bounded-chamber PCB drone digital prototype

Assessment date: 23 October 2026. This is an integration specification, not an
executed project or a claim of complete present capability. There is no measured
global complexity maximum: mesh size, supported physics and coupling fidelity
are different limits. This is the most demanding coherent target identified
within the requested demonstration scope.

Update: `propulsion_pod/coupled/` now contains an executed compiled-C /
reciprocal two-phase linear P1 FEM / hover-BEM closed loop with native project,
field histories and exact KiCad companions. This closes a synthetic reference
milestone; the real VESC/three-phase motor, blade CFD, thermal coupling and full
drone gates below remain open. See `propulsion_pod/coupled/README.md`.

## System and build sequence

Use an open-source PCB drone as the flying article, with its original battery
and propulsion ratings. Put it in an authored bounded chamber. Include its
controller PCB, ESC stages, motors, propellers, radio antenna, current/voltage
sensing and enclosure or frame. Keep sources and licenses distinct.

Start with one restrained propulsion pod. Establish circuit/controller/motor
closure and measured or independently referenced force, loss and temperature
checks before expanding to four motors and six-degree-of-freedom flight.
Restriction to a stationary pod is an integration milestone, not fulfillment
of the requested flying-drone example.

Use a separate 48 V power-electronics test article for the requested 48 V to
1.8 V, 50 W planar-transformer converter. Do not silently power a low-voltage
drone board from 48 V. This companion article can share chamber studies and
demonstration tooling without inventing an electrically compatible assembly.

| Study | Visible result | Present evidence and remaining work |
| --- | --- | --- |
| Battery/bus PI and sensing SI | Voltage sag, ripple, ringing, ADC input histories | Existing reduced board-derived circuit examples; full board extraction and qualification remain separate. |
| SPIKES controller and ESC | PWM, phase currents, backEMF, sensed signals | Existing illustrative Studio circuits and averaged motor example; actual controller-driven motor FEM closure remains required. |
| Motor electromagnetics and motion | Rotor position, field, torque and speed histories | Existing prescribed-current machine FEM does not establish controller feedback, propeller loading or flight. |
| Propeller flow and chamber CHT | Air velocity, pressure and PCB/motor/case temperature | Bounded laminar/creeping-flow and CHT owners exist; rotating-propeller CFD and qualified moving-body coupling remain required. |
| Thermal and structural response | Hotspots, sink contact effects and displacement | Existing transient thermal examples and bounded static thermoelastic owner; no inference of general transient structural/FSI support. |
| Antenna, EMI and RI | Radiation and induced/sensed responses | Existing antenna radiation example; its chamber is visual geometry only. Chamber scattering, calibrated emissions and RI response remain required. |
| Touch input | Finger-position-dependent capacitance and controller response | Geometry-resolved finger/return-path solver and verification remain required. |
| Planar magnetics companion | Winding/core fields, losses, temperature and output ripple | Native KiCad/STEP assembly, ideal circuit and separate imposed-heat results exist. Actual winding/core field extraction and conservative circuit/thermal feedback remain required. |
| Bounded flight | Attitude, thrust, trajectory and wall interaction | No completed coupled demonstration; controller, rotor flow, force integration and rigid-body closure must be established first. |

## What can honestly be presented now

The existing packs support a multi-study engineering showcase. Opening several
results on one assembly does not make them one coupled simulation.

The documented Studio board bridge supports actual two-way resistor-temperature
feedback with lumped thermal nodes and electrical energy accounting. Its bounded
contract permits 128 circuit elements, 32 thermal nodes, 2,000 windows and two
million replay steps with a 120-second cooperative budget. It excludes
semiconductors, spatial thermal fields, airflow and FEM deformation. These are
limits of that bridge, not universal limits of SPIKE.

The separate dielectric AC-to-heat-to-static-elasticity chain and sampled EM
network/circuit-resistor heat bridge provide additional bounded coupling paths.
Neither establishes the complete drone chain. Existing Python templates and
worker execution do not establish a general graphical coupled-study editor or
native GUI visual acceptance.

## Completion gates

1. **Reproducible sources:** exact adjacent KiCad inputs for every PCB-based
   `.spike`; portable libraries and STEP assets; source revision, license,
   material provenance, units and hashes. Respect upstream redistribution terms.
2. **Separate studies:** each domain has a saved executable request, actual raw
   result, independent benchmark and declared validity range. Record failures.
3. **Propulsion pod closure:** controller outputs drive the electrical model;
   current drives motor fields; computed torque and propeller load update speed;
   backEMF and sensors return to the controller. No prescribed-speed substitute.
4. **Conservative coupling:** account for electrical input, stored field and
   kinetic energy, shaft work, fluid work and physical heat. Keep numerical
   dissipation separate. Verify transfer maps and avoid counting losses twice.
5. **Refinement and stability:** define tolerances before runs; refine electrical
   and coupling steps and field/fluid meshes; exercise startup, load change,
   stall and cooling loss. Do not infer convergence from solver completion.
6. **Whole drone:** validate thrust/torque against independent references, then
   integrate all rotors and bounded rigid-body dynamics. Test hover and a small
   commanded maneuver before wall interactions. A geometric boundary alone does
   not establish wall aerodynamics or collision behavior.
7. **Recording:** reopen exact projects in SPIKE and SPIKES; execute through GUI
   or supported in-app Python templates. Save real transient frames and plots.
   Record smooth playback of computed results; disclose accelerated time and
   edits. Do not label playback as real-time solving.

Finger touch, full core fields, motor/controller closure and chamber immunity
remain mandatory targets rather than optional omissions. The solver and
multiboard chats have already been asked to implement the missing capabilities.
This assessment does not claim that work has landed.

## Suggested flagship film

Use a 60–90 second edited sequence after the relevant gates pass: assembly and
native sources; startup/PWM/current; rotor field and backEMF; airflow and heat;
bus disturbance and sensing; chamber EMI/RI; bounded hover. Use the planar
converter and finger-touch scene as separate short companion films so their
physics and electrical operating points remain understandable. Until the
coupling gates pass, publish clearly separated study clips only.

## Repository evidence reviewed

- `docs/SOLVER_STATUS.md`
- `docs/STUDIO_BOARD_COSIMULATION.md`
- `docs/EMERGE_COSIMULATION.md`
- `docs/CFD_TETRA_WORKFLOW.md`
- `docs/validation/EMERGE_RELEASE_INTEGRATION_20261023.md`
- `docs/validation/PLANAR_MAGNETICS_DEMO_20261023.md`
- Existing promo pack source inventories and native projects.

Recheck these contracts when implementation changes. New physics requires the
derivation, primary references, numerical evidence and review specified by
`docs/NUMERICAL_METHOD_EVIDENCE.md`; a compelling animation is not validation.
