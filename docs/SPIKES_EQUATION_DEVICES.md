<!-- SPDX-License-Identifier: Apache-2.0 -->
# User-defined semiconductors and package parasitics

## Executable scope

`python/spikes/equation_device.py` builds inert library subcircuits from ordered
terminals and user-defined branch current and charge equations. Material names
are metadata, not a hard-coded family list: a future diamond device can use
this interface when its equations and coefficients are available. A material
label alone never creates a physical model. The illustrative bundled examples
are neither measured diamond models nor qualified HEMT compact models.

Each branch supplies `current_a`, `charge_c`, or both, with paired positive and
negative terminals. Native current is

`i(p -> n) = I(V, t, parameters) + dQ(V, t, parameters)/dt`.

Branch contributions enter opposite terminal KCL rows, so their algebraic
terminal-current sum is zero. Differential terminal voltage references make
the constitutive expression invariant to common-mode translation. Cross-terminal
charge dependencies are permitted, but reciprocity, stored-energy passivity,
material applicability and physical consistency remain the model author's
responsibility. No dimensional checker is implied by recorded SI units.

The builder validates a bounded expression tree and resolves parameters; it
does not evaluate model physics in Python. The existing C++ behavioral DAG
evaluates values and derivatives, and native MNA/Newton and capacitor state
integration execute the generated circuit. There are no Python callbacks or
finite-difference charge derivatives during simulation.

## Charge transformation

For a user branch Q, choose a positive numerical reference capacitance Cr.
An auxiliary behavioral voltage source imposes `vq = Q/Cr`. A zero-volt series
sense source feeds capacitor Cr. A current-controlled behavioral source copies
the sensed capacitor current into the physical terminal pair. Thus
`Cr * d(vq)/dt = dQ/dt`; Cr cancels and is not added to physical terminal
capacitance. The auxiliary circuit is a numerical construction, not a physical
package or an energy observable. Do not include its source power in device-loss
reports. Obtain physical power from terminal voltage/current pairs.

Backward Euler produces `(Q[n]-Q[n-1])/h`; constant-step BDF2 produces
`(1.5 Q[n]-2 Q[n-1]+0.5 Q[n-2])/h`. Tests compare these exact discrete values
for `Q(v)=1e-9*(v+v^3/3)` under a voltage ramp. Nonlinear differential
capacitance is `dQ/dV`, not the input `Q/V`. This allows explicit Cgs, Cgd/Miller,
Cds, junction and field-plate charge laws supplied by a user without inventing
their bias dependence. Cr affects conditioning: choose it near the expected
capacitance scale and check convergence. Auxiliary unknowns cost memory/runtime.

Original clean-room implementation and elementary KCL/calculus derivation;
no third-party model source or coefficients were used. Tests establish
electrical/discrete-integration behavior, not semiconductor physics validation.

## Build and run a reusable library

```powershell
python -m python.spikes device-build examples/spikes/equation_devices/hemt_illustrative.json --spice-output user-hemt.lib -o user-hemt-report.json
```

Library export refuses to overwrite an existing `.lib`. Imports/building never
load native code. Include the resulting subcircuit in a project explicitly;
the ordinary native runner executes its B/C/V primitives. Waveform parsing
requires the existing native-extensions option. The report records resolved
expressions, pin order, parameter units, material notes and unqualified status.
Expressions may refer only to differential V(pin,pin) on declared pins, supported
bounded mathematical functions, parameters and time. File operations, Python
syntax, external current references and arbitrary directives are rejected.

## Package composition across device families

`compose_device_parasitics` accepts any named core subcircuit and ordered pins:
diode, BJT, MOSFET, HEMT, IGBT, thyristor, controlled switch, or a new family.
There is no automatic substitution of a missing device core.

```python
from python.spikes.device_parasitics import compose_device_parasitics

package = compose_device_parasitics(
    'USER_HEMT', ['D', 'G', 'S', 'FP'], name='PACKAGED_HEMT',
    pin_parasitics={
        'D': {'resistance_ohm': .01, 'inductance_h': 2e-9},
        'G': {'resistance_ohm': 1, 'inductance_h': 3e-9},
        'S': {'resistance_ohm': .01, 'inductance_h': 1e-9},
    },
    between_pin_parasitics=[
        {'pins': ['G', 'S'], 'capacitance_f': 1e-12,
         'leakage_resistance_ohm': 1e12},
    ],
)
```

Package R/L joins external pins to private core pins. Shunt C/leakage joins the
private core pins. A zero-valued series network uses an exact zero-volt link,
not an invented resistance. Arbitrary substrate, Kelvin/source-sense and
field-plate pins are preserved. Avoid double counting capacitances already
included in the core. Supply actual fitted/measured values; zero/default values
are not an estimate of a real package.

Optional signed mutual inductance coefficients are checked against the full
inductance matrix for passivity. They export standard `K` elements, which are
currently unsupported by the owned parser/runner; select an explicit compatible
backend or omit them. No silent fallback is performed. Core dependencies are
retained as inert text separately, never automatically appended or executed.

## Still incomplete

This does not supply all parasitic effects for every semiconductor. Trapping,
dynamic R_on, transit/tail/recovery states, self-heating, temperature-dependent
parameters, avalanche, distributed/frequency-dependent packages, correlated
noise and aging need explicit models and separate evidence. Arbitrary internal
state DAEs, automatic dimensional analysis and a graphical equation editor are
not supplied by this builder. General compiled compact-model extensions remain
separate; see the [ngspice OSDI model workflow](https://ngspice.sourceforge.io/osdi.html)
as an interoperability reference, not evidence that SPIKES supports every model.

Only operating point and native BE/BDF2 transient are tested here. AC/noise,
hybrid integration, HEMT switching qualification and manufacturer agreement are
not established. Existing core support restrictions still apply through wrappers.
Human numerical review is mandatory before release; installers are unchanged.
