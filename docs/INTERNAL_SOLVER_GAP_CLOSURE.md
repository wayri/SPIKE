# Internal solver capability closure

Checkpoint: 2026-09-06. These are execution boundaries, not UI permissions.

## Current evidence

- Owned SPICE process probe is available, ABI 1, experimental. Transient,
  persistent sessions, source updates, checkpoints, integration selection and
  sparse-solver options are exposed. Eleven workspace/process tests passed.
  Its reviewed structured workspace is not arbitrary raw-netlist execution or
  closed-loop geometry/circuit multiphysics.
- The separate SPIKES 0.3.0-beta.1 process reports `verification_only` and
  `serial_reference`. It exposes diffusion references and prepared compact
  frequency-domain Maxwell/modal/rational-network verification jobs. These
  require prepared validated operators/meshes, not raw PCB geometry.
- No callable internal NF2FF/far-field, airflow/Navier–Stokes or conjugate-heat
  route was established. Manager registration cannot supply these algorithms.
- Public structured-solid thermal references are not an enclosure/airflow/CHT
  product solver. Missing OpenFOAM/openEMS adapter coverage is separate from
  missing internal SPIKES functionality.

## Ordered implementation contracts

| Workstream | Required next executable slice | Evidence before enabling product workload |
| --- | --- | --- |
| Owned circuit | Implemented: live-probed structured workspace workload and manager-to-workbench engine selection | 16 manager tests and 11 workspace/process tests pass; OP/DC and transient only; no AC, raw-netlist or geometry-cosimulation promotion |
| Prepared Maxwell adapter | Implemented: prepared frequency-domain verification jobs mapped through the public process boundary | 11 adapter tests and real prepared modal fixture checks reported by solver-owner task, including hash/stale-operator negatives; remains verification-only |
| PCB full-wave | Conforming material/port mesh, port excitation and result extraction connected to native Maxwell | Waveguide/line/launch convergence, power balance, calibrated dielectric/conductor treatment and independent correlation |
| Far field | Radiation boundary/PML plus surface-field-to-far-field operator and exported angular/frequency results | Dipole/power/directivity, PML/refinement, near/far conservation and independent reference checks |
| Solid thermal | Real PCB/contact/material/source geometry connected to native solid field execution | Contact/anisotropy/transient conservation and mesh/time convergence; measured/independent reference |
| Conjugate thermal | Fluid velocity/pressure/energy equations and conservative fluid-solid interface transfer | Flow/convection benchmarks, interface heat balance, fan/boundary models and coupled convergence |
| Circuit/field/thermal coupling | Explicit ports and conservative iterative exchange with residuals | Coupling stability, energy balance, timeout/cancellation/restart and correlated fixtures |

The manager must distinguish unavailable runtimes, incomplete adapters, and
missing workload capabilities. Existing approximate/experimental labels must
survive selection. No silent solver replacement or removal of geometry checks.

## Packaging

Frontend owned-workbench, readiness-label and viewport-focus checks pass,
as do TypeScript and architecture validation. The workbench honors the persisted
manager choice on opening, permits explicit engine changes, and starts no solve
as a side effect of selection. This is not a full-suite or packaged regression run.

Manager source integration and status-label changes follow archived 0.2.10.
They require rebuild/installation and packaged-runtime parity before claiming
availability in the installed application. The full capability set above is
not complete or production-qualified.
