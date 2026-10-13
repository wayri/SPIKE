<!-- SPDX-License-Identifier: Apache-2.0 -->
# Generic passive model equations and validation

`python/spikes/passive_models.py` contains independently authored generic
linear RLC and four-terminal Kelvin-shunt source generation. These are original
SPIKE equations, code and fixtures derived below from circuit conservation and
constitutive laws, not imported or translated vendor models or external source
code. There is no manufacturer fit, material characterization or device rating.
Knowledgeable human review of this numerical code is required before release.

## API and units

`build_model(kind, value, **parameters)` accepts `resistor`, `capacitor`,
`inductor` or `kelvin_shunt`. It returns name, kind, ordered pins, native SPICE
subcircuit source, effective primary value, admitted parameters and limitations.
Name is an ASCII identifier. Value is strictly positive in ohms, farads, henries
or ohms respectively. Resistance, inductance and capacitance parameter suffixes
state SI units. Temperatures are Celsius; temperature differences are kelvin.
All numeric inputs must be finite; bool and string values are not admitted.
Missing parasitics default to zero and are omitted, not assigned guessed values.
`leakage_resistance_ohm=None` means no leakage resistor. An explicit leakage
resistance must be positive. Zero-contact Kelvin connections are exact 0 V
source branches, not tiny resistors. External ideal-source loops can therefore
be singular; the circuit solver must report that failure, not regularize it here.

Example (source generation, not a hardware-qualified model):

```python
from python.spikes.passive_models import build_model, impedance
model = build_model("capacitor", 1e-6, name="MY_CAP",
                    series_resistance_ohm=0.1, series_inductance_h=1e-9)
source = model["source"] + "V1 in 0 1\nX1 in 0 MY_CAP\n.op\n"
z_ohm = impedance(model, 1e6)
```

## Static tolerance and temperature

For primary nominal value q0, tolerance p in percent, deterministic corner
c in [-1, 1], and dT = T - Tref:

    q = q0 * (1 + c*p/100) * (1 + tc1*dT + tc2*dT*dT)

`tc1_per_k` has units K^-1, `tc2_per_k2` has units K^-2. The tolerance is
restricted to [0, 100); effective q must stay strictly positive and finite.
Temperatures must exceed absolute zero. Corner 0 selects nominal; -1 and +1
select tolerance endpoints. There is no statistical distribution. Only the
primary value changes: contact and parasitic values remain the explicit inputs.
Coefficients are supplied by the user; no unmeasured temperature law is implied.
This is a constant source-generation adjustment, not a dynamic thermal model.

## Two-terminal network

Pins are P, N. A series chain contains optional Rs, optional Ls, then the
primary element. Cp and optional Rleak each bridge the complete external P/N
pair. In particular, capacitor leakage is external to its ESR/ESL chain in
this topology. This convention is explicit and is not interchangeable with
placing leakage across only the internal ideal capacitor.

From v=Ri, v=L*di/dt and i=C*dv/dt, under exp(j*w*t), w=2*pi*f:

    Zbody = R, j*w*L, or 1/(j*w*C)
    Zseries = Rs + j*w*Ls + Zbody
    Y = 1/Zseries + j*w*Cp + 1/Rleak
    Z = 1/Y

Absent branches contribute zero admittance. A zero series impedance is an
exact short. At DC the ideal capacitor branch is open; its model impedance is
Rleak if present and explicit `complex(inf, 0)` otherwise. A lossless exact
parallel resonance similarly returns infinity. No finite ceiling is substituted.
The analytic API is only two-terminal; Kelvin requests fail explicitly.

For a capacitor with ESL, imaginary impedance vanishes at
f0=1/(2*pi*sqrt(Ls*C)); at f0 it equals ESR when shunt branches are absent.
The corresponding LC parallel resonance has zero total admittance and infinite
impedance in the ideal lossless case. Near a lossless resonance cancellation
makes relative error ill-conditioned; no resonance-width or loss claim follows.
Floating-point overflow/underflow that prevents a finite calculation raises
ValueError. There is no frequency extrapolation qualification or inferred skin
effect, dielectric dispersion, bias dependence, saturation, hysteresis or noise
characterization. User-selected RLC parameters do not establish RF accuracy.

## Kelvin shunt

Pin order is FP, FN, SP, SN. Each force contact has Rc; the body R connects SP
to SN. SP and SN are physical sense connection nodes, not buffered outputs:

    FP -- Rc -- SP -- Rbody -- SN -- Rc -- FN

For force current I and an infinite-impedance sense measurement,
Vsense=I*Rbody and Vforce=I*(Rbody+2*Rc). A finite differential sense load Rm
changes the sensed network resistance to Rbody*Rm/(Rbody+Rm); sense loading
is not silently ignored. Common-mode sensing loads require a full node solve.
RLC and leakage extras are rejected for Kelvin; contacts are rejected for the
two-terminal kinds. This bounds interpretation instead of ignoring parameters.

## Independent acceptance evidence

`tests/python/test_spikes_passive_models.py` verifies DC open/short limits,
the algebraic R/(1+j)=R/2-jR/2 oracle, capacitor series resonance, parallel
resonance with and without explicit loss, coefficient units/scaling, invalid
input rejection and native parser topology. Optional actual owned C++ tests
verify Kelvin force/sense voltages with finite sense loading and ideal/finite
contacts, plus RC and RL transient step responses. For backward Euler and zero
initial state, RC voltage/Vstep and RL current/(Vstep/R) equal
1-(1+h/tau)^(-n). RC time-step halving must reduce continuous-solution error
by approximately a factor of two. These tests assert values, not plot shapes.

Run `python -m unittest discover -s tests/python -p test_spikes_passive_models.py -v`.
Native tests use `SPIKES_TEST_LIBRARY`, `SPIKES_TEST_NATIVE_LIBRARY`, or
`SPIKES_NATIVE_LIBRARY`, then `build-peec-native/spikes_c_api.dll`; if no library
exists they are explicitly skipped. Passing software fixtures does not establish
hardware qualification, solver coverage outside these cases, or release approval.
