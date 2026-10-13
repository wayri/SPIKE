<!-- SPDX-License-Identifier: Apache-2.0 -->
# PWM coupling to retained PCB and package volumes

The experimental headless mode replaces the winding's embedded thermal RC with
explicit retained tetrahedral volumes. Winding, high/low switch and load losses
are all deposited in declared cells. Only winding resistance feeds temperature
back into the present bounded synchronous-buck electrical model. It is not
arbitrary semiconductor switching-loss or full-board accuracy qualification.

## Input and execution

Use `pwm_volume_electrothermal.run_pwm_volume_electrothermal(request)` or worker
method `run_pwm_volume_electrothermal` with exactly `{ "request": request }`.
Worker method `validate_pwm_volume_electrothermal` performs admission without
loading a native DLL. It does prepare admitted thermal matrices, unlike the
lightweight admission for the older lumped mode.

The request contract is `spike/pwm-volume-electrothermal-request/v1`. Supply:

- `parameters`: existing buck electrical/control parameters, excluding
  `thermal_resistance_k_per_w` and `thermal_capacitance_j_per_k`.
- `thermal.request`: an admitted `spike/assembly-tetra-thermal-request/v1`,
  including retained mesh, conductivity, contact faces and ambient boundaries.
  Volumetric heat sources must be absent or zero to prevent duplicate heating.
- `thermal.material_heat_capacity`: density in kg/m3 and specific heat in
  J/(kg K) for every material, with explicit material IDs.
- `thermal.initial_temperature_k`: scalar or vertex-ordered Kelvin array,
  exactly agreeing with fixed-temperature boundaries.
- `thermal.device_cell_fractions`: exactly Rw, SH, SL and Load. Each maps to
  unique `{cell_id, weight}` entries with positive weights summing to one.
- `coupling`: optional controls in an object: `cycles_per_window` (default 1),
  `maximum_iterations` (20), `temperature_tolerance_k` (1e-6),
  `relative_energy_tolerance` (1e-6), and `relaxation` (1).

For occurrence-bound PCB/package meshes use the existing
`assembly_field_thermal.bind_assembly_field_thermal` handoff's compiled thermal
request and cell identity maps; do not use display offsets or guessed body IDs.
Expand heat capacities with `assembly_field_transient.remap_field_transient_settings`
before passing compiled occurrence material IDs. This API consumes already
retained conforming volumes, not a new PCB CAD importer or automatic device map.

Reproduce original numerical fixtures with the existing local native DLL and
separately installed CalculiX:

```powershell
.venv/Scripts/python.exe examples/converter/run_pwm_volume_validation.py --library build-peec-native/spikes_c_api.dll --output-dir build/pwm-volume-new
```

Use a fresh directory; evidence cannot overwrite an earlier run. The example
retains exact requests/results, switched ODE histories, actual CalculiX
histories and input/source/runtime hashes. Its low-capacity homogeneous cube is
an analytical fixture, not physical PCB material or measured hardware.

## Reusable thermal step and independent derivation

`prepare_retained_thermal_step(thermal_request, material_heat_capacity,
device_cell_fractions)` returns a prepared sparse kernel with `node_count`,
`validate_temperature`, `device_temperatures_k` and
`advance(old_temperature_k, dt_s, device_energies_j, cancel_check=None)`.
Advance is stateless: an unsuccessful trial cannot mutate old temperatures.
The stiffness/capacity matrices are reused; solver factorizations are not
claimed to be cached. Every mapped device must appear in every energy input.

For device d and cell c, fraction a_dc deposits `a_dc E_d/4` at each tetrahedron
vertex. The resulting map W has column sums one, so `1^T W E = sum(E)`.
The transpose `W^T T` samples the same deposition region for feedback. Overlap
between different devices is permitted; a device may not duplicate a cell.

The reused solid kernel solves `M (T_new-T_old)/dt + K T_new + radiation = load`,
with consistent tetrahedral capacity `M_e = rho cp V (I+11^T)/20` in J/K.
Stored thermal energy change is `1^T M (T_new-T_old)`, never `T^T M T/2`.
Convection/radiation outward loss, prescribed inward flux and fixed-temperature
reactions are separate signed terms. Finite thermal contacts exchange equal
and opposite heat and do not appear as an external source.

The PWM solver integrates each switching edge explicitly and records Joules
per device from native endpoint powers. Physical L/C energy and backward-Euler
numerical dissipation are separated; numerical dissipation is not deposited as
heat. The combined energy ledger includes electrical storage, solid storage,
physical boundary exchange and numerical dissipation.

For each macro trial, restore electrical history from the same native snapshot,
reset sampled-PI controller state to its start value, and replay complete PWM
cycles with winding temperature fixed to the start/end midpoint estimate.
Advance solids with energy-equivalent constant per-device window powers.
Commit only when both the unrelaxed nodal endpoint defect and successive
per-device energy defects pass. Relaxation cannot hide a defect. Failed or
cancelled trials restore the snapshot and publish no trial frames or energy.

The derivation independently composes the existing native switched-MNA and
[retained thermal weak form](ASSEMBLY_THERMAL_TRANSIENT.md). Code, equations,
fixtures and documentation are independently authored; no external solver
source or dataset was copied. Established finite-element and energy invariants
are not claimed as novel research.

## Output, validation and recovery

Result v1 contains committed volume frames, per-window device Joules,
transpose-gathered temperatures, feedback temperatures, electrical cycle
endpoints, coupling defects/iterations, separate and combined energy ledgers,
request/state digests and the native DLL hash. Model status is experimental.

Mapping/temperature/resource errors fail admission. A nonpositive R(T),
temperature outside the bounded electrical feedback range, failed native solve,
energy imbalance or coupling nonconvergence fails explicitly. Cancellation
returns `cancelled` with only committed windows; it is not portable resume.
No hidden retry reduces a timestep or weakens a tolerance.

Budgets: 8 MiB control request, two million maximum replay electrical steps,
200,000 retained nodal frame values, 100 cycles/window and 100 trial iterations.
The reusable thermal adapter additionally bounds retained mesh and dense mapping
memory. Standalone callers must supervise process time/memory; registered worker
operations are process-contained, but this is not installed-GUI qualification.

[Retained correlation evidence](validation/PWM_VOLUME_CORRELATION_20261010.md)
records actual runs. Uniform history agreement does not conceal nonuniform
DC3D4 centroid-capacity versus consistent-P1 differences. Per-design mesh,
window and electrical-step convergence, physical material/model suitability,
measured correlation and knowledgeable human review remain necessary before
sign-off use. No release package was rebuilt by this implementation.
