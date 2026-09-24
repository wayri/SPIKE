# Component thermal calculations

The Thermal GUI can run steady state and transient component temperatures using
the built-in SPIKE lumped thermal solver. OpenFOAM and external runtimes are not
required. These results are **approximate engineering prechecks**, not validated
PCB temperature fields. Results retain the supplied part reference.

For each included component supply dissipation in W and top/bottom thermal
resistances in K/W. Each resistance is the **complete effective path from the
component temperature node to the specified ambient**, including package,
interface, heatsink/board and ambient transfer as appropriate. A datasheet
junction-to-case resistance alone does not describe that entire path. There is
no automatic extraction of these paths from ODB++ geometry or a BOM. A missing
side is an open (adiabatic) path. An object needs a path to a fixed thermal sink,
either through these resistances or through explicit surface boundaries and
other objects. Passive objects can have zero dissipation.

Transient runs also need heat capacity in J/K, a duration and a time step. The
default initial component temperature is ambient; an explicit initial
temperature permits cooldown calculations with zero power. Power, ambient,
resistance and heat capacity remain constant throughout a run. Steady results
report branch heat flows; transient results report temperature samples including
time zero and the requested end time. Reduce the time step and compare the
temperature trace to assess time discretization error.

## Worker contract

`run_component_thermal` accepts parameters:

```json
{
  "scenario": {
    "mode": "transient",
    "ambient_temperature_c": 25,
    "run": {"end_time_s": 60, "write_interval_s": 0.5}
  },
  "components": [{
    "component_ref": "U1", "power_w": 6,
    "resistance_top_c_per_w": 10, "resistance_bottom_c_per_w": 5,
    "thermal_capacitance_j_per_c": 3, "initial_temperature_c": 25
  }]
}
```

`mode` is `steady_state` or `transient`. Temperature differences in C and K are
identical; the historical `c_per_w` and `j_per_c` field names therefore express
K/W and J/K without a conversion. References must be nonempty and unique,
case-insensitively. Booleans, negative dissipation, nonfinite numbers,
nonpositive resistances/capacities and temperatures below absolute zero fail
with structured `COMPONENT_THERMAL_INPUT_INVALID` diagnostics. Missing or invalid
inputs yield no fabricated result rows. No simulation process is launched.

The result uses `spike/thermal-result/v1`: `status`, `model_status`, `mode`,
`ambient_temperature_c`, `nodes`, `links`, `transient`, `summary`, `issues` and
`provenance`. Every node contains its `component_ref`, supplied properties,
`steady_temperature_c`, `temperature_rise_c`, `heat_flow_top_w`,
`heat_flow_bottom_w` and `temperature_c`. Branch flows always describe the
**steady solution**. `temperature_c` is the end-of-run temperature for transient
mode, or the steady temperature for steady state. Transient frames have
`time_s` and a reference-keyed `temperatures_c` map. Summary reports total power,
maximum steady/final temperatures and the steady energy-balance residual in W.
Provenance records normalized inputs, solver ID and the lack of field or
production qualification. GUI callers should display diagnostics and allow
editing and rerunning on failure.

## Object and surface boundaries

The worker request optionally includes a `surfaces` array (at most 2,048 rows).
Each enabled row has a unique `id`, an `object_ref` matching a component reference,
a `surface` label, a `kind`, and an optional boolean `enabled` (default true).
`surface` may be `whole`, an axis face such as `+Z`, or a stable surface label
of up to 128 characters. Surface names retain assignment identity; all surfaces
of an object share that object's one temperature node.

| Kind | Required parameters | Fixed sink |
| --- | --- | --- |
| `conduction` | Positive `resistance_c_per_w` (K/W); `target_ref` is another included object or `ambient` (default) | Optional `ambient_temperature_c` when target is ambient |
| `convection` | Positive `heat_transfer_coefficient_w_m2_k` (W/m²/K), positive `area_mm2` | Optional `ambient_temperature_c` |
| `radiation` | `emissivity` in (0,1], positive `area_mm2` | Optional `surroundings_temperature_c` |

Missing sink temperatures use the scenario ambient. Temperatures must be finite
and at least -273.15 C. To model zero transfer, disable or remove the boundary;
zero resistance, area, coefficient or emissivity is not admitted. Unknown
objects, self conduction, duplicate enabled IDs, and floating groups fail
closed. `ambient` is reserved and cannot be a component reference. Disabled
rows do not participate in the solve. Conduction and convection are linear;
radiation retains its fourth-power dependence on absolute temperature.

For example, `surfaces` may contain both of these entries on the same face:

```json
[
  {"id":"air-U1", "object_ref":"U1", "surface":"+Z", "kind":"convection",
   "area_mm2":1000, "heat_transfer_coefficient_w_m2_k":10},
  {"id":"rad-U1", "object_ref":"U1", "surface":"+Z", "kind":"radiation",
   "area_mm2":1000, "emissivity":0.8, "surroundings_temperature_c":25}
]
```

All assigned boundaries and legacy top/bottom paths add together. Remove a
legacy path when it already includes the new convection or contact boundary,
otherwise its heat removal is counted twice. Area is explicit and editable;
the worker does not infer exposed area, contact area, occlusion or view factors
from geometry. Convection is a prescribed coefficient and bulk fluid temperature,
not a solved fluid flow. Radiation assumes a gray surface facing large fixed
isothermal surroundings with view factor one; it does not model radiation
between finite objects. Conduction uses a supplied effective resistance and
does not infer material conductivity or PCB spreading.

Results include `surfaces` with normalized active inputs and `heat_flow_w` for
each branch. Positive heat flow leaves `object_ref`; an interobject conduction
branch deposits that same power in `target_ref`. Branch flows describe the
steady solution even in transient mode. In addition to the global steady
residual, the summary includes `max_node_energy_balance_error_w` and
`max_transient_energy_balance_error_w`, both in W.

## Independent derivation and numerical evidence

Let `u = T - Ta` be rise above ambient, `G = 1/Rtop + 1/Rbottom` the total
conductance in W/K, `P` the dissipation in W and `C` the heat capacity in J/K.
Conservation of energy gives `C du/dt + G u = P`; the steady equation is
`G u = P`. Summing each branch's `u/R` reproduces P. The component adapter
constructs two explicit ambient links per component and reuses
`thermal_network.py`; it does not introduce another thermal physics kernel.

Backward Euler gives `(G + C/dt) u[n+1] = P + (C/dt) u[n]`. Its homogeneous
amplification factor `C/(C + G dt)` lies in (0,1), so the admitted positive
system has no time step stability restriction and no overshoot for constant
inputs. Stability does not imply accuracy: the scheme has first-order time
error. Actual `dt = end/ceil(end/requested_step)` never exceeds the requested
step. The analytical transient oracle is
`u(t) = P/G + (u(0) - P/G) exp(-G t/C)`.

For the original uncoupled top/bottom model each equation is scalar, with no subtraction of nearly equal matrix
entries or coupling conditioning problem. The diagonal kernel avoids dense
elimination. Extremely unrepresentable conductances, temperatures or totals
fail closed. Finite floating point arithmetic still limits resolution when
temperature rises are much smaller than the absolute ambient temperature.

`tests/python/test_component_thermal.py` supplies synthetic independent oracles:
6 W with 10 and 5 K/W parallel paths gives a 20 K rise and 2/4 W branch flows;
cooldown with C=3 J/K has a 10 s time constant. Tests assert steady energy
balance to 1e-12 W, stepwise discrete transient energy to 1e-11 W, steady-limit
agreement to 1e-6 K, monotone heating/cooling, and error reductions greater than
1.9 when halving time step (first-order convergence). Existing coupled network
tests remain applicable. The derivation, implementation and fixtures were
authored independently from first-law conservation, with no external source
implementation, data or assets copied or adapted.

For explicit surface boundaries, conservation at object i is
`C_i dT_i/dt + sum(q_out) = P_i`. Conduction contributes `(T_i-T_j)/R`,
convection `h A (T_i-T_air)`, and radiation
`epsilon sigma A ((T_i+273.15)^4-(T_surroundings+273.15)^4)`.
Areas convert from mm² to m² with 1e-6. The rounded SI value
`sigma = 5.670374419e-8 W/(m² K⁴)` is documented in
[NIST's 2022 CODATA table](https://physics.nist.gov/cuu/Constants/Table/allascii.txt).
Only the physical constant is sourced; all derivations, implementation and
synthetic fixtures are independently authored and no external code was used.

The surface kernel uses damped Newton iteration and a backward Euler storage
term. Its Jacobian is the conductance Laplacian plus positive ambient,
radiation (`4 epsilon sigma A T_K^3`) and transient storage diagonal terms.
Connected paths to fixed sinks remove floating modes at positive temperatures.
A 1 K derivative floor supplies a nonzero descent direction at absolute zero.
The fourth-power difference is evaluated as `(T-S)(T+S)(T²+S²)` in kelvin to
reduce cancellation. Each accepted solve has per-node residual divided by
`max(1 W, |power|, |storage|) + sum(|branch power|)` no larger than 1e-10.
Temperatures below absolute zero, nonfinite arithmetic, singular elimination,
or failure within 120 Newton iterations/80 damping attempts return no results.
Large conductance contrasts can still lose temperature resolution; the
residual checks do not certify a condition number or physical applicability.

Additional synthetic tests check a coupled two-object series path, additive
legacy paths, convection area conversion, sink temperature overrides,
radiation against the independent fourth-root steady solution, and mixed
convection/radiation transient energy balance to 1e-8 W. Halving time steps
demonstrates first-order convergence for the mixed boundary transient. These
checks establish numerical behavior for those fixtures, not board validation.

## Bounds and limitations

There are at most 256 objects, 2,048 surface boundaries, 10,000 time steps and 100,000 component
samples. Increasing the step or reducing duration recovers from an output limit.
Coupled surface runs also have a conservative 50,000,000 dense work-unit budget.
With N objects, preflight charges N³ times the number of transient steps plus
one steady solve; each actual Newton factorization then consumes N³ units from
the same maximum run budget. This bounds nonlinear iterations as well as the
requested sample count. The budget is an algorithmic operation proxy, not a
wall-clock guarantee. Fewer objects, a larger time step, or a shorter duration
can recover a blocked request. Objects without interobject conduction use the
diagonal solve and do not incur this dense budget. Legacy runs without surface
boundaries retain their existing diagonal route and limits.
The bounded calculation runs in the worker; per-request cancellation is not
implemented. Existing worker process termination remains the cancellation
boundary. No internet or optional native library is needed.

The model excludes PCB copper spreading, geometry-derived heat paths,
temperature-dependent material properties, radiation view factors, CFD,
distributed enclosures and spatial fields. Explicit resistances, convection
coefficients and radiation assumptions must be provided and their
applicability reviewed. Numerical oracle verification does not establish
measured-board correlation. Knowledgeable human review remains required before
release of numerical changes.
