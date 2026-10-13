# Retained tetrahedral solid thermal transients

`assembly_tetra_transient.py` advances a three-dimensional temperature field on
the same admitted, conforming P1 tetrahedra used by the steady thermal reference.
`assembly_field_transient.py` binds the field to retained board and STEP-derived
solid occurrences, with explicit materials, sources, matched contacts and source
provenance. The result remains experimental and not production qualified.
Meshing or UI availability does not establish accuracy for an arbitrary assembly.

## Desktop workflow and original benchmark

1. Open a saved `.spike` assembly and its multi-board workspace. Open the
   retained volume thermal study in the coupled studies section.
2. Prepare reviewed board/STEP volumes, materials, heat sources, contacts and
   ambient boundaries. Choose **Transient** and supply density and specific heat
   for every material, initial temperature, duration, integration step and output
   interval. These properties are never inferred from a model's appearance.
3. Choose the internal thermal solver or CalculiX and run. Internal solves show
   computed frames while running and support cancellation. CalculiX currently
   returns a completed history in a batch; it does not stream intermediate
   temperatures. In-progress previews cannot be saved as completed results.
4. Use **Play**, the simulated-time slider and playback speed to inspect the
   saved frames. The color range stays fixed across the history and occurrence
   filters. Playback follows physical simulated time, selecting solved frames
   without interpolating uncomputed temperatures.
5. **Save with results** retains settings and every admitted frame inside the
   `.spike` package. Reopening shows the retained history directly. Setup-only
   saves preserve inputs and omit results. Geometry changes retire old results.

The independently specified benchmark and its analytical, time refinement,
mesh refinement and actual CalculiX comparisons are recorded in
[validation evidence](validation/ASSEMBLY_THERMAL_TRANSIENT_20261008.md).
Generate its native package and full evidence using:

```text
.venv/Scripts/python.exe scripts/validate_transient_thermal.py
```

This requires configured real Gmsh and CalculiX runtimes. It writes
`.local/transient-thermal-validation/original-transient.spike`, containing two
homogeneous board volumes, an original STEP package volume, a finite thermal
contact and five saved CalculiX frames. The minimal source is an original
numerical fixture, not a production PCB or a reproduction of the Fang board.
The result remains experimental; agreement between solvers is not measured
hardware validation.

## API and settings

```python
from python.spike_core.assembly_field_transient import run_assembly_field_transient

settings = {
    "contract": "spike/assembly-tetra-transient-settings/v1",
    "duration_s": 10.0,
    "time_step_s": 0.05,
    "output_interval_s": 0.5,
    "initial_temperature_k": 300.0,
    "material_heat_capacity": [
        {"material_id": "reviewed-material", "density_kg_m3": 2700.0,
         "specific_heat_j_kgk": 900.0}
    ],
    "power_schedule": [
        {"time_s": 0.0, "scale": 0.0},
        {"time_s": 2.0, "scale": 1.0},
        {"time_s": 10.0, "scale": 1.0}
    ]
}
result = run_assembly_field_transient(request, problem, settings,
    progress_callback=lambda frame: print(frame["time_s"], frame["maximum_k"]),
    cancel_check=lambda: False)
```

This example needs an existing admitted retained `request` and `problem`, and
one reviewed density/specific-heat record for every authored material. The
illustrative material values are user inputs, not an automatic material choice.
The initial temperature may instead be a Kelvin list in the assembled vertex
order. It must exactly agree with all prescribed fixed-temperature nodes.
Conflicting initial and fixed states fail admission, so an instantaneous boundary
reset cannot silently create or remove unreported initial stored energy.

The optional power schedule is a bounded, strictly increasing piecewise-linear
list spanning exactly zero through duration, with finite nonnegative scales.
It multiplies every authored volumetric source together. It does not scale
prescribed face heat flux, fixed temperatures, convection or radiation inputs.
Omitting it means a constant scale of one. All times are seconds; density is
kg/m^3, specific heat is J/(kg K), conductivity is W/(m K), and outputs use K.

`run_assembly_tetra_transient(request, settings, *, progress_callback=None,
cancel_check=None)` accepts the existing thermal tetrahedral request plus these
separate settings. Material IDs are the tetra request's IDs. In the field
wrapper they are the original retained request's physical material IDs;
`remap_field_transient_settings` expands these into occurrence material IDs.
`validate_field_transient_settings` performs setup-only admission.

The kernel returns `spike/assembly-tetra-transient-result/v1`; the wrapper
returns `spike/assembly-field-transient-result/v1`. Both declare transient mode.
The wrapper retains original settings, their digest, assembly/request/handoff/
problem digests, source traceability, final occurrence extrema, and an overall
result digest. `verify_assembly_field_transient_result` checks these bindings,
all retained times/nodal arrays, initial and fixed states, energy identities,
final cell fluxes, contact flows, and numerical/status claims. This is shape and
consistency admission, not cryptographic solver authenticity.

`field_result.frames` contains the initial frame, requested output instants and
the final frame. Each frame contains `time_s`, `node_temperatures_k`, extrema,
`stored_energy_change_j`, and the last accepted step's `heat_balance` (null at
zero). Final fields, fluxes, contact flows and fixed-node reactions are also
available directly in `field_result`. A frame's heat balance covers its last
integration step, not the interval since the preceding output frame. Integrated
`energy_balance` covers every internal step, including steps without a frame.

Progress callbacks receive independent frame copies only after solve acceptance.
They are provisional until the full run completes. Cancellation raises an error
and never returns a partially completed result as success. Checks occur before
and after geometry admission, per assembled cell, per step, inside CG/Newton,
and after callbacks. The existing bounded geometry audit itself is synchronous.

## Independent derivation and conservation

For constant cell density `rho`, specific heat `cp`, conductivity tensor `k`,
and affine tetrahedral shape functions `N`, the weak equation is

`M dT/dt + K T + R(T) = f(t)`.

Integrating barycentric monomials over a tetrahedron gives
`integral(N_i N_j) = V/10` for equal indices and `V/20` otherwise. Therefore
`M_e = rho cp V (I + 11^T)/20`, in J/K. This is the exact consistent capacity.
`K_e = V B k B^T`, in W/K, uses the admitted constant gradients. The same
triangular surface moments as the steady reference supply convection and
reciprocal matched contact blocks. Ambient radiation reuses the exact
degree-five surface integration and consistent tangent in
`assembly_tetra_radiation.py`.

Backward Euler gives `M (T_new-T_old)/dt + K T_new + R(T_new) = f(t_new)`.
The sparse solve uses temperature increments to avoid constructing and
subtracting large `M*T/dt` load vectors. Symmetric diagonal scaling precedes
bounded conjugate gradients. The tangent is positive definite on free nodes
because the consistent capacity is positive definite for positive cell volume,
density and specific heat. Consequently isolated adiabatic bodies are valid
transient problems and need no steady-state temperature anchor.

Radiation uses at most 80 damped Newton updates and 30 backtracks per update,
with positive Kelvin bounded by 10000 K and a true residual acceptance test.
The residual tolerance includes an explicit floating-point arithmetic floor
for nearby-temperature subtraction. Reported relative residual uses the larger
of the physical load scale and that floor divided by the relative tolerance.
Absolute residual and energy acceptance tolerances are retained as well.

The integration grid is the union of the nominal step grid, output times and
source knots. No step exceeds the requested step size. Floating-point-equivalent
derived events are merged, preferring authored source knots; indistinguishable
distinct source knots are rejected. Output requests can therefore shorten
integration steps. Source power is sampled at each step endpoint, so a linear
power ramp has first-order temporal quadrature error, not an exact ramp integral.

Summing nodal equations eliminates internal conduction and contact power.
Fixed-node reactions include both the consistent capacity and static boundary
terms. Every accepted step verifies

`source + inward_flux + fixed_reaction - convection - radiation - storage_rate = 0`,

where `storage_rate = 1^T M (T_new-T_old)/dt`. Summed step energies must agree
with `1^T M (T_final-T_initial)`. Energy tolerances combine a relative physical
power allowance and a bound on matrix/temperature arithmetic roundoff. The
initial Kelvin baseline does not enter the stored-energy change by subtraction
of two large absolute stored-energy values.

## Evidence and limits

Run the original fixtures with:

```text
python -m unittest tests.python.test_assembly_tetra_transient -v
python -m unittest tests.python.test_assembly_transient_persistence -v
```

The tests establish exact insulated uniform heating and stored energy; a
single-free-node tetrahedron whose continuous semidiscrete decay is exponential
and whose backward-Euler decay is exact at each discrete step; first-order
error reduction under step halving; contact exchange and separate adiabatic
bodies; prescribed flux, convection and nonlinear radiation energy accounting;
and a regular tetrahedron's nonlinear radiation history against independently
bisected scalar heat balance. They also cover event-time arithmetic, malformed
and excessive requests, cancellation/nonconvergence, callback isolation, mixed
board/solid provenance, and tampered saved results. The persistence suite passes
real solved frames through offline import/export and native `.spike` saves,
retains settings when results are stripped, rejects rehashed malformed histories
atomically, and withholds results after physical assembly placement changes.

The single-free-node oracle has `tau = rho*cp/(10*k) = 1 s`. Its exact
continuous temperature is `300+10 exp(-t)` K and its BE result at one second is
`300+10(1+dt)^(-1/dt)` K. The tests assert this discrete result to 1e-9 K and
error ratios between 1.8 and 2.1 for steps 0.2, 0.1 and 0.05 s. This isolates
temporal convergence from spatial error. A single successful solve never claims
temporal convergence; each result sets `temporal_convergence_verified=false`.

The limits are 10000 integration steps, 1001 retained frames and 200000 total
frame-node samples, in addition to the existing 10000-node/5000-cell geometry
budgets and the field wrapper's 8 MiB serialized envelope. Smaller output
intervals increase memory. Density, heat capacity, conductivity, boundaries and
contacts are constant in time and independent of temperature. No phase change,
fluid transport, enclosure radiosity, or moving/nonmatching contact is modeled.

Consistent P1 capacity does not guarantee a nodal maximum principle on arbitrary
coarse meshes. Local overshoot can occur even while total energy is conserved;
negative Kelvin is rejected. Mesh and time-step refinement, material review,
and appropriate independent comparisons are required for a particular model.
Steady retained-geometry limitations continue to apply. Knowledgeable human
review of this numerical code is required before release.

All new equations, implementation and fixtures were independently authored from
the polynomial integration and energy identities above. No external solver
source, comments, example meshes or test data were copied or adapted. The
separate CalculiX comparison records external executable evidence and any
discretization differences; it does not replace these independent oracles.
