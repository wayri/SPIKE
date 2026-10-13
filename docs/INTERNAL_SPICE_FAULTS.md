# Internal SPIKES parameter faults

The persistent owned SPIKES engine supports bounded parameter perturbations
before its next accepted step. This is an engineering approximation of the
specified circuit change, not a validated universal model of device damage.
All implementations and regression oracles here are original SPIKE work;
no third-party implementation or device data was copied.

## Parameters and physical interpretation

| Setter | Eligible element | Native bounds | Interpretation |
| --- | --- | --- | --- |
| `set_resistance(id, ohm)` | Ordinary resistor | 1e-6 to 1e15 ohm | Resistance change, finite short, or degraded bridge |
| `set_mosfet_threshold(id, volt)` | NMOS Level-1 | -100 to 100 V | VTO shift; other model parameters remain fixed |

To approximate gate oxide or gate-source shorts, provision a resistor between
gate and source before creating the session. To approximate a body-diode
short with bulk tied to source, provision a resistor between drain and source.
For a separate bulk terminal the corresponding junction bridge is drain to
bulk and must be selected explicitly. A healthy 1e12-ohm
shunt introduces a finite leakage and must be included in baseline validation.
Decrease that resistor to an explicit finite resistance to inject the fault.
Use a finite resistor between any two explicitly selected nodes for a degraded
resistive bridge. Zero resistance and topology changes are rejected. Large
conductance ratios can still cause poor conditioning or failure to converge;
bounds are admission limits, not a promise of convergence for every circuit.

Unsupported devices, unknown IDs, nonfinite values and out-of-bounds values
fail before changing circuit parameters or accepted state. In particular this
interface does not mutate PMOS, WBG, OSDI, electrothermal resistor, or arbitrary
compact-model parameters. No semiconductor aging rate is inferred by a setter.

## Python and C boundaries

`python.spikes.fault_injection.FaultSite` is a frozen descriptor containing
`name`, `element_id`, `parameter`, `healthy_value`, `minimum`, `maximum`, and
`mechanism`. `parameter` is `resistance_ohm` or `threshold_voltage_v`.
`apply_fault(session, site, value)` checks the site's tighter bounds and calls
the native setter. `reset_fault(session, site)` restores its immutable healthy
value at the current simulation time. Wrappers retain their original initial
checkpoint for full reset, including source values, time and physical state.

```python
from python.spikes.fault_injection import FaultSite, apply_fault, reset_fault

site = FaultSite("oxide_bridge", "R_gate_shunt", "resistance_ohm",
                 1e12, 10.0, 1e12, "finite gate-source bridge")
apply_fault(session, site, 100.0)
assert session.step(1e-6), session.message
reset_fault(session, site)
```

The C functions `spikes_transient_session_set_resistance` and
`spikes_transient_session_set_mosfet_threshold` are additive ABI-1 symbols.
Existing layouts and calls are preserved. Python exposes
`library.session_fault_parameters_available`; calling setters with an older
library raises `NativeABIError`. Callers must use the exact compiled library
path and must not claim fault support merely because ABI version equals 1.

## State and integration semantics

A setter changes the next solve's parameters; it does not rewrite the last
accepted sample or advance time. After a successful parameter change, matrix
factorizations are cleared. Physical dynamic state, including capacitor
voltage, inductor current, diode history and OSDI state, is retained. The
integration order restarts with backward Euler at the discontinuity, then
hybrid trapezoidal or BDF2 resumes. The parameter-change flag bypasses the
parameter-bearing history signature only for these topology-preserving
validated session edits, and is consumed by the next successful solve.

Checkpoints contain circuit parameters, sources, accepted samples, time,
diagnostics and integration history, including a pending discontinuity.
Failed steps preserve the accepted physical state and position. A previously
accepted parameter edit remains pending after a failed step; restore a
checkpoint to roll back that edit as well. Diagnostics may report the failed
attempt. This is distinct from clearing a fault at the current time.

## Independent numerical evidence and limits

`tests/python/test_spikes_fault_injection.py` exercises the actual selected DLL.
The RC oracle derives directly from `C dv/dt = (Vs-v)/R`: on each constant-R
segment, `v(t+h) = Vs + (v(t)-Vs) exp(-h/(RC))`. The tests use 1-us steps,
R of 1/2 kohm, C of 1 uF and absolute voltage tolerances 50/20 uV for the
two segments. Discontinuity restart is checked against the backward-Euler
recurrence `(v_old + h*Vs/(RC))/(1+h/(RC))` to 1e-12 V. Fixed terminal NMOS
tests check the saturation equation `Id = KP*(W/L)*(Vgs-VTO)^2/2 + Goff*Vds`
with body tied to source and lambda zero. Finite gate/drain bridges use
independent voltage-divider expectations. Tests also cover invalid input,
checkpoint replay and failed-step recovery. A zero-bias dynamic diode with
initial charge independently checks `q[n] = q0/(1+h/tau)^n` through a parallel
resistor mutation, demonstrating hidden-charge continuity. An RL fixture checks
inductor-current continuation against its backward-Euler recurrence. The standalone
`tests/test_spikes_fault_injection.cpp` exercises the C ABI directly.

Run with an explicit rebuilt engine:

```powershell
$env:SPIKES_TEST_NATIVE_LIBRARY = 'C:/path/to/spikes_c_api.dll'
python -m unittest tests.python.test_spikes_fault_injection -v
```

These fixtures validate numerical parameter mutation within their stated
models. They do not qualify radiation, wearout, avalanche, oxide rupture,
thermal destruction, real semiconductor lifetime, or physical short geometry.
Numerical changes still require knowledgeable human review before release.
