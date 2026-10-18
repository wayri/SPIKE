<!-- SPDX-License-Identifier: Apache-2.0 -->
# Initialized network-port reflectometry: SI07-S10

Experimental, production-unqualified. This API executes one
[initialized RLC transient](RLC_INITIAL_STATES.md) and reports incident/reflected
voltage, an apparent reflection ratio, apparent voltage/current impedance and
signed instantaneous power at one explicit fitted-network port. It advances
SI07 reflectometry diagnostics without qualifying spatial TDR reconstruction,
instrument calibration or measured network extraction. SI07 remains open.

## Physical question, plane and governing identities

The reference plane is the fitted-network port. Current I is positive **into
the fitted network**, using the parent's `port_current_a_by_port`, not the
Thevenin source current before its boundary shunt capacitance. The external
series R/L and shunt C remain part of the experiment but outside this plane.
The reference Z0 is the supplied common positive real reference impedance in
ohms. Supplied fitted/L/C initial states and all other source drives remain
active; no source is silently terminated or removed.

For real instantaneous normalized waves a and b in sqrt(W), define voltage
waves in volts, at each requested observation:

```
Vplus  = sqrt(Z0) * a
Vminus = sqrt(Z0) * b
V = Vplus + Vminus
I = (Vplus - Vminus) / Z0
p_network = V * I = (Vplus^2 - Vminus^2) / Z0 = a^2 - b^2
```

The implementation uses the actual parent's a/b and network V/I, checks the
two reconstruction identities, and computes signed power from V*I. These are
instantaneous real quantities, with no RMS conversion or phasor factor 1/2.
The power is transported across the plane; it is not automatically heat.

Where admitted by explicit floors:

```
gamma_apparent(t) = Vminus(t) / Vplus(t)
Z_apparent(t) = V(t) / I(t)
```

Eliminating Vplus/Vminus gives the algebraic relation
`Z_apparent=Z0*(1+gamma_apparent)/(1-gamma_apparent)` when its denominators are
nonzero. The code computes V/I directly; it does not divide by a numerically
small `1-gamma`. For a memoryless resistor Rload at the plane, I=V/Rload gives
`gamma=(Rload-Z0)/(Rload+Z0)` and `Z_apparent=Rload` during every resolved sample,
independently of the external source R/L/C dynamics.

For a network with memory or multiple driven ports these instantaneous ratios
depend on the full excitation and initial state. They are not frequency-domain
impedance, a characteristic impedance, isolated S11, or a material property.
The common real wave reference is a normalization convention; an arbitrary
fitted network does not become a physical uniform TEM line through this API.
Active models and stored-energy release can produce negative power/impedance
or a reflection ratio outside [-1,1]. Those values are retained without clipping.

## Referenced physics and independently authored derivation

Reviewed 18 October 2026: David H. Staelin, *Electromagnetics and Applications*
(2011), chapter 7, section 7.1.2, equations (7.1.6)–(7.1.7) and
(7.1.16)–(7.1.18), printed pages 187–189: instantaneous TEM voltage/current
wave decomposition and transported power; section 7.2.2, equations
(7.2.1)–(7.2.8), printed pages 199–200: time-domain junction continuity,
reflection ratio and impedance mismatch.
[Official MIT chapter](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/790b8f65328723ec194cb440b303f8fb_MIT6_013S09_chap07.pdf).

The fixed-plane inversion, instantaneous power identity, floor/status policy
and same-state loaded-RLC interpretation above are independently derived from
those foundations and the existing parent wave convention. The parent method
ledgers retain physical KCL/KVL, stable rational realization and propagator
lineage. No third-party source code, figures, example data or implementation
was copied. No dependency, integrator or old public numerical contract changes.

## Public contract, unresolved values and workflow

Worker method `run_network_reflectometry` accepts exactly `{'request': ...}`.
Request contract `spike/network-reflectometry-request/v1` has exactly:
`contract`, `transient_request` (initialized RLC v2), `probe_port`,
`minimum_incident_voltage_v`, `minimum_current_a`. The probe must be a known
source-network port; both floors must be finite strictly positive numbers.

Reflection is resolved only if `abs(Vplus)>minimum_incident_voltage_v`.
Otherwise `reflection_coefficient=null` and
`reflection_status='incident_below_floor'`. Impedance requires resolved incident
voltage and `abs(I)>minimum_current_a`. Otherwise `apparent_impedance_ohm=null`
with `impedance_status='incident_below_floor'` or `'current_below_floor'`.
Equality with either floor is unresolved. Missing ratios do not discard finite
raw waves, voltage, current or power. A near-open response can have resolved
reflection near +1 while impedance remains unresolved. No infinity, epsilon
regularization, substituted zero or fabricated large impedance is returned.

Result contract `spike/network-reflectometry-result/v1` retains the full actual
initialized transient result, full original-request SHA-256 digest, probe,
reference impedance, explicit floors, points and diagnostics. Each point has
`time_s`, `incident_voltage_v`, `reflected_voltage_v`, `network_voltage_v`,
`network_current_a`, `instantaneous_network_power_w`, `reflection_coefficient`,
`reflection_status`, `apparent_impedance_ohm`, `impedance_status`.
Diagnostics retain one actual solution, sample/resolution counts and maximum
absolute voltage/current reconstruction errors. Original-request digests use
canonical sorted compact UTF-8 JSON, non-ASCII preserved and nonfinite forbidden.

Strict registered 2020-12 schemas enforce status/null consistency; runtime also
checks source/state/probe identity, finite arithmetic and numerical resources.
Run the original 75-ohm resistor experiment with external source R/L/shunt-C:

```powershell
.venv/Scripts/python.exe examples/network_reflectometry/run_reflectometry.py
```

## Numerical analysis, admission and verification

One actual parent fit/trajectory is executed. Original transient/state, probe,
floors and full nested-result estimate are admitted before fitting. Parent
work is bounded by 100 million and request/result bytes by 8/16 MiB; final
actual result size is checked. The complete original source/initial state and
parent output remain authoritative. Cancellation or numerical failure returns
no successful partial result.

Wave normalization, reconstruction, ratios and signed products must remain
finite and representable. Voltage/current reconstruction acceptance is
`2e-10 SI + 1e-9 * scale`. The voltage scale is the maximum magnitude of
network V, Vplus, Vminus and reconstructed V; current scale is the maximum
magnitude of network I and reconstructed I. No passivity threshold is imposed
on intentionally active models. A physically valid waveform can be rejected
when the selected representation or arithmetic is unresolved.

Dividing by small incident voltage or current amplifies input/fit errors.
First-order perturbations have the forms
`delta_gamma ~ (delta_Vminus - gamma*delta_Vplus)/Vplus` and
`delta_Z ~ (delta_V - Z*delta_I)/I`. Caller floors provide absolute numerical
admission thresholds, not measurement noise estimates, relative conditioning
certificates or guaranteed ratio accuracy. The raw observations, thresholds
and statuses support a later uncertainty model rather than hiding that issue.

Verification uses independent analytic loaded-RLC references, known resistor
mismatch, physical fitted-memory/network-current references, multiple ports,
common initial state, reference/time scaling, observation refinement and
unresolved floor/sign/open behavior. Physical V/I comparisons use 2e-10 SI
absolute plus 1e-9 relative, with ratio-specific tolerances retained in tests.
No new discretization is introduced: parent PWL interval propagation remains
unchanged. Observation refinement tests shared-sample invariance, not omitted
time extrema or new broadband fit accuracy. See the
[executed record](validation/SI07_NETWORK_REFLECTOMETRY.md).

## Multiphysics ownership and remaining scope

Probe/source/initial-state identity and signed network power preserve the
boundary needed for later cross-domain work. A network can absorb power into
internal storage or deliver stored energy; p_network is not a deposition law.
For continuous source/network work, external resistor heat and boundary L/C
storage, run the [energy ledger](RLC_ENERGY_LEDGER.md) on the same full request.
Sampled power is not a continuous energy quadrature or thermal transfer.

Fixture calibration, isolated echo extraction, distance/velocity mapping,
distributed impedance reconstruction, mixed-mode probe calibration, physical
VNA/TDR correlation, nonlinear drivers, uncertainty qualification, thermal
ownership and production readiness remain separate gates. The existing SI
workflow's frequency-to-time TDR path is unchanged. Human knowledgeable
numerical review remains required before release; full PI/SI parity stays open.
