<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent propeller-flow interface audit — 23 October 2026

**Result: no executable SPIKE interface found that solves actual rotating propeller blades in stationary air and returns torque/thrust to advance the motor state.** Existing whole-frame rotation, stationary enclosure flow, supplied-load surface transfer, reduced motor dynamics and imposed-loss thermal studies cannot satisfy the requested motor–propeller coupling. This is a code/status audit, not an attempted propeller simulation or an independent validation of the author's separate pod thermal starter.

## Concrete existing owners and limits

| Owner | Executable operation | Missing for this request |
| --- | --- | --- |
| `python/spike_core/enclosure_rotating_frame.py`, `solve_enclosure_rotating_frame` | Steady constant-Ω whole-domain co-rotating closed rectilinear enclosure; relative velocities, Coriolis momentum and centrifugal pressure recovery | Every obstacle/wall co-rotates. No blade-to-stationary-air boundary, rotor/stator interface, moving mesh, time-varying shaft Ω or propeller traction integration. Explicitly not a propeller solver; no worker route. Rotation-number admission ≤20 and relative-flow Re≤20 remain. |
| `enclosure_rectilinear_momentum.py` / `enclosure_cht_v2.py` | Stationary obstacle-bearing laminar momentum; CHT v2 re-solves momentum/heat on supplied rectilinear cuts | Stationary walls/voxel masks; no rotating blades or turbulence. Re upper admission20. Changing body-force arrays or drawing moving streamlines would not add blade physics. |
| `enclosure_flow_analysis.py`, `analyze_enclosure_flow` | Probes/streamline reconstruction of caller-supplied stationary MAC fields | No new momentum solution, unsteady pathline, blade pressure/shear or thrust prediction. Exterior/solid face velocities must be exactly zero. |
| `coupled_surface_exchange.py` | Conservative mapped caller-supplied heat or Cartesian traction, plus adjoint work/power identity | Does not compute fluid traction. Face areas/overlap assertions have no spatial quadrature positions, so no moment/angular-momentum guarantee. No time master or two-way FSI. |
| `service_cfd.py` | Fixed methods: native/SU2 cavity, cavity CHT, enclosure CHT/v2, tetra CHT and supplied surface exchange | No propeller/rotor method. Both enclosure catalog entries explicitly state `rotating_machinery:false`; catalog registration or external-runtime detection does not execute a rotor coupling. |
| `em_machines.py` | Constant-parameter reciprocal reduced PM machine with supplied shaft torque | The shaft load is supplied, not returned by blade-resolved fluid stresses; not a solved motor/propeller participant loop. Planar magnetic-machine fields elsewhere explicitly exclude CFD coupling. |

`docs/SOLVER_STATUS.md` lines107–110,125–131,164–169 and432–437 retain these exclusions. `docs/ENCLOSURE_FLOW_RESEARCH.md` identifies rotation as an isolated in-process research API. `docs/INTERNAL_CFD_AND_FSI_PLAN.md` stages external aerodynamic loads in CFD-03, rotating machinery in CFD-05, and moment-preserving mechanical transfer in CFD-07. CFD-04 is additionally required if the selected physical regime needs a turbulence closure; CFD-06 is relevant if compressibility/tip-Mach conditions require it. Full flexible-blade FSI (CFD-08) is separate from a first rigid-rotor shaft coupling and must not be claimed by a rigid study.

## Exact missing mechanisms for the solver development chat

1. **Physical rotating blade fluid participant.** Admit the actual blade/hub wetted geometry, fluid domain and source identity, rotating/stationary regions and consistent boundary normals. Implement a bounded stationary-environment MRF/interface method for an appropriate steady case, or conservative moving-boundary/ALE/sliding topology for transient motion. Whole-enclosure rotation is not this interface. Preserve continuity/momentum and, for moving grids, geometric conservation; demonstrate independent rotating-wall/interface checks before a propeller claim.
2. **Torque, thrust and rotor work from solved stresses.** Integrate pressure plus viscous traction at spatial quadrature locations. For declared shaft unit axis a and origin r0, retain `F=∫t dA`, `τ=∫(r−r0)×t dA`, `T=a·F`, and signed shaft torque `a·τ`. Preserve resultant, moment and interface power across transfer; current area-only exchange cannot establish this moment. Numerical reference pressure must be consistent on the complete wetted surface. Do not reinterpret a zero-mean cavity gauge as an arbitrary open-surface load.
3. **Actual motor–fluid state coupling.** With aero torque positive against rotation, advance a declared shaft equation `J dω/dt=τ_em−τ_aero−τ_bearing` using actual participant returns. Feed accepted ω/angle back to the rotating fluid boundary and back-EMF/electrical participant. For fixed rigid geometry, even the smallest steady coupled operating-point solve must actually resolve torque balance between the motor and fluid; a polynomial or lookup load surrogate is outside the requested blade-resolved coupling.
4. **One accepted state and energy accounting.** Define common physical time/windows, subcycling/interpolation, interface residuals, convergence and trial/accepted states. Transient failures must roll back every participant, not leave motor or fluid advanced. Audit signed `P_shaft=τ_aero ω` against fluid moving-wall work, kinetic-energy storage, pressure/kinetic fluxes and viscous dissipation with applicable thermal/total-energy terms. Coriolis force's zero work in an isolated co-rotating benchmark does not prove this rotor energy transfer.
5. **Bounded independent acceptance.** Retain exact requests/results, geometry/material/runtime digests and failed-state suppression. Check mass, force/moment signs, zero-speed/rotation-reversal limits, angular momentum and shaft/fluid work. Demonstrate spatial, outer-domain, rotor-interface and time/coupling refinement as applicable; compare a geometry-matched independent/measured propeller case with uncertainty. The current manufactured enclosure benchmarks cannot be relabeled as propeller validation.

These are missing implementation/admission mechanisms, not merely absent UI controls. A visible shaft STEP, a controller dashboard, a completed cavity or three separate study windows do not close them.

## Minimum case inputs needed before an honest executable request

- Exact licensed blade/hub CAD or adequately resolved section/chord/twist/pitch/radius data; blade count, handedness, pitch convention, shaft axis/origin and installation coordinates. A nominal cylinder/box motor envelope and display shaft supply none of the blade geometry.
- Physical domain and installation: open-air or chamber/duct boundaries, inlet/far-field velocity/pressure/temperature, wall/clearance geometry, outlet treatment, fluid density/viscosity and any justified compressible/thermal properties. State operating Re/Mach range and required closure/wall treatment rather than assuming every propeller fits Re≤20.
- Motor/electrical inputs: exact supported motor constitutive parameters/geometry, inverter/controller model or explicitly declared drive, supply and limits, shaft/rotor/propeller inertia, bearing/friction law, initial ω/angle, and mechanical attachment identity. A VESC PCB imported as geometry does not determine these values.
- Coupling specification: sign/unit/frame contracts (m,s,rad,N,N·m,W), time horizon/steps or steady operating-point convergence, coupling tolerances/rollback, blade traction quadrature and motor–fluid torque port. Flexible blade properties are needed only if flexibility/FSI is explicitly in scope.
- Independent validation case and permitted reference data with geometry, operating conditions, uncertainty and redistribution provenance. Supplying inputs alone does not complete the missing solver mechanisms above.

## Evidence identity and audit boundary

The audit read the named source owners and status/planning records, and searched the CFD worker registry plus installed extension/source declarations for propeller, rotor, MRF/sliding, traction and torque interfaces. No native/external propeller simulation or capability run was executed. No surrogate load law, new physics, solver edit, app edit or release-status change was made. No conclusion about an unrelated external solver's intrinsic capabilities is implied.

| Exact inspected file | SHA-256 |
| --- | --- |
| docs/SOLVER_STATUS.md | 6c6c471b6267a383345abfc1ec56fa0e53c28f4fc0e49f9be19fc883ba7a573e |
| python/spike_core/enclosure_rotating_frame.py | 06143bad2daab0c948a88aa380de151b5cbbf816e1cdb1f59f249f94e6bc6f78 |
| python/spike_core/enclosure_rectilinear_momentum.py | 983f3be5d6df13e1141fcc325e2c5920e4c2a4b66cf0be51f11e7eb98b64ac99 |
| python/spike_core/enclosure_cht_v2.py | 3a44c115abd11c57b01a86bfde5c4705a951c4e4aab25b07cc15e24257363738 |
| python/spike_core/coupled_surface_exchange.py | 4c0466288a13ea01a817a845d7628860c95b68afeb7f99a45c1b3916e9726312 |
| python/spike_core/service_cfd.py | 7ba39060d20f41aab09c8266e18ab398c7f57df2f7c710a3d8f242e02ad8fb65 |
| docs/INTERNAL_CFD_AND_FSI_PLAN.md | c3096cdf4017b230cadf5a82ee59690629c59d3aeead013fc68812f5b22b8a5a |

Existing prerequisite derivation/primary-source review: `docs/validation/TURBULENCE_ROTOR_REQUIREMENTS_20261020.md`. It explicitly separates the implemented whole-frame mathematical checks from rotor/stator and measured-propeller acceptance. Knowledgeable human numerical review remains necessary; this audit itself does not authorize or qualify a new rotating-flow implementation.
