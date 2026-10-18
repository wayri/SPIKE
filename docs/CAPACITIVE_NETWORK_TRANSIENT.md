<!-- SPDX-License-Identifier: Apache-2.0 -->
# Shunt-capacitive fitted-network source/load transients

SI07-S04 adds a supplied shunt capacitor across selected fitted-network ports,
driven by a finite-resistance Thevenin source. It complements the existing
[resistive](TERMINATED_NETWORK_TRANSIENT.md) and
[series-inductive](INDUCTIVE_NETWORK_TRANSIENT.md) boundaries. This is an
experimental zero-initial-state LTI calculation, not general circuit/DAE,
nonlinear receiver, physical broadband or thermal-coupling qualification.

## Public contract and topology

Call `run_capacitive_network_transient(request)` from
`python.spike_core.sparameter_capacitive_terminated`, or the worker method of
the same name with exactly `params: {request: ...}`. Run the original example:

```powershell
.venv/Scripts/python.exe examples/capacitive_network_transient/run_rc.py
```

`spike/capacitive-network-transient-request/v1` contains `fit_request`,
`terminations`, `output_times_s`. Each source port has exactly one boundary
with `port_name`, `resistance_ohm`, `capacitance_f`, and continuous PWL
`voltage_points` (`time_s`,`voltage_v`). Capacitance is nonnegative and at least
one port must have C>0. Positive C requires R>0. C=0 retains the prior resistor
boundary, including a well-posed ideal voltage source when R=0. Zero source
voltage describes a load. R is between the ideal source and port; C is shunted
from port to its reference node. It is not a series capacitor.

All source waveforms begin at time zero and share a positive horizon; output
times are strictly increasing and inside that horizon. Fitted states and capacitor
voltages initially equal zero. Missing port loads, nonzero initial values,
extrapolated source waveforms and implicit geometry/material models are not inferred.
The actual supplied-pole fitter executes and its complete source/model result is
retained in `spike/capacitive-network-transient-result/v1`.

## Physical equations and independently derived wave closure

Current Inet is into the fitted network; Isrc is through the source resistor
toward the port. With common positive real reference impedance Z0,

```text
V = sqrt(Z0) (a+b),     Inet = (a-b)/sqrt(Z0)
Isrc = (Vs-V)/R = Inet + Csh dV/dt       [Csh>0,R>0]
```

The fitted model is `b=D a+Cm x`, `x_dot=A0 x+P a`, with stacked pole states
x in sqrt(W), A0 blocks `-pk I`, and P blocks `pk I`. Cm concatenates the
residue matrices. It is distinct from the supplied physical capacitance Csh.

For positive Csh define `v=V/sqrt(Z0)=a+b`, in sqrt(W). The capacitor algebraic
row is `(I+D)a=v-Cm x`. Csh=0 instead uses the existing resistor row
`(I-Gamma D)a=Gamma Cm x+u`, where
`Gamma=(R-Z0)/(R+Z0)` and `u=sqrt(Z0)/(R+Z0) Vs`.
At positive-Csh ports normalize the source as `u=Vs/sqrt(Z0)`.

Stack the mixed rows to solve `M a = Nx x+Nv v+Nu u`. Capacitor rows of M are
the corresponding rows of I+D, with Nx=-Cm, Nv selecting their own voltage
state and Nu=0. Resistor rows use I-Gamma D, Nx=Gamma Cm, Nv=0 and Nu selecting
their own normalized source. Solve for `a=Qx x+Qv v+H u` without an inverse.

KCL gives the physical capacitor state evolution:

```text
alpha = 1/(R Csh),     beta = 1/(Z0 Csh)
v_dot = alpha u + (beta-alpha) v - 2 beta a
```

Substitution yields a constant combined state problem `z_dot=A z+F u`,
z=[x,v]. The existing dimensionless augmented-exponential construction advances
`[z,u,delta_u]`, all in sqrt(W), exactly for each continuous PWL interval up
to floating-point computation. The interval grid includes source corners and
requested observation times; transitions are cached by duration. Output-grid
invariance is tested. Refining that grid does not establish source-fit accuracy.

For an independent parallel RLC reference the fitted network is an ideal
inductor: `L dInet/dt=V`. Combining KCL and the component laws gives
`Csh V''+(1/R)V'+(1/L)V=Vs'/R`, with the initial derivative determined by
the undifferentiated KCL. This distinguishes the parallel topology and damping
from the earlier series RLC fixture. Resistor-network RC references instead use
`Csh V' = Vs/R - V(1/R+1/Rload)`.

## Source current, loss and energy for future coupling

Every observation reports `source_current_a_by_port` separately from
`port_current_a_by_port`. Positive-C ports additionally report capacitor voltage
and derivative. `boundary_residual_a_by_port` is `Inet+Csh*dV/dt-Isrc`;
resistive/ideal-source rows retain their algebraic voltage checks separately.
The result preserves source port ordering, capacitor-port ordering, original
fit/boundaries/input digest, final fitted states and final capacitor voltages.

Actual supplied resistor loss is `R Isrc²`, **not R Inet²** when current splits
through the shunt capacitor. Stored capacitor energy is `.5 Csh V²`. They obey
the independently checked boundary power identity

```text
Vs Isrc = V Inet + R Isrc² + Csh V dV/dt
```

Typed instantaneous voltage/current/derivative, watts and joules can feed later
coupling contracts. This stage does not integrate heat into a thermal mesh,
infer material/temperature/winding laws, expose steppable session state or assign
physical energy to generic fitted-network states. A physical inductor reference's
known energy is a test oracle, not a generic state-energy feature.

## Admission, limits and unsupported cases

Require a regular mixed feedthrough matrix: minimum singular value at least
`1e-10*max(1,sigma_max)`, condition at most 1e10 and backward error at most
1e-10. The full connected model must be numerically resolved and asymptotically
stable, with positive decay margin and relative construction-scale margin above
1e-10. These floating-point checks do not certify robust stability for arbitrary
nonnormal systems or uncertain parameters. Stable active networks may be admitted;
sampled passivity is not imposed as a universal source property.

Check finite precision, normalized mixed-row/KCL and capacitor-voltage-state
residuals. Limits include 32 total dynamic states and augmented dimension 48
including capacitor states, 1,024 intervals/observations, 128 distinct durations,
100 million estimated work, 8 MiB request and 16 MiB result. The dimensionless
exponential-generator norm is bounded by 1e6. Underflow/overflow and unsupported
precision ranges fail explicitly. Cancellation polls surround bounded operations;
failure/cancellation returns no successful partial result.

Some well-defined circuits, including direct-feedthrough constraints from parallel
ideal capacitors, require a descriptor formulation or topology-aware state
reduction and are rejected. Combined arbitrary RLC/nonlinear boundaries, mutual
capacitance in the boundary, time-varying components, arbitrary initial values,
marginal systems and ideal sources on capacitor ports are outside this stage.
No physical accuracy outside the source fit band, measured causality/passivity,
general receiver behavior or complete SI/PI parity is established.

## Reviewed primary references and provenance

Reviewed 18 October 2026. Equations, code and synthetic reference fixtures are
independently authored. No external implementation, diagram, mesh or test fixture
is copied. The [numerical evidence policy](NUMERICAL_METHOD_EVIDENCE.md) applies.

| Source | Reviewed method/locator and use | Applicability limits |
| --- | --- | --- |
| David H. Staelin, *Electromagnetics and Applications*, text copyright 2011, [MIT OCW 6.013-hosted notes](https://live.ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/d3be4ea78b036a6362230fb41780cf54_MIT6_013S09_notes.pdf). | Reviewed sections 3.1.3, 3.4.1, 3.5.1–3.5.2: capacitor law (3.1.12), energy (3.1.16), KCL (3.4.3), parallel RLC equations (3.5.25)–(3.5.31) and Thevenin/Norton discussion. Independently derive the mixed wave/state problem and physical oracles from these laws. | Ideal lumped elements and charge accounting; this does not establish arbitrary sampled-field broadband accuracy or supply the SPIKE algorithm. |
| SciPy 1.17.0 [`scipy.linalg.expm` Notes/References](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.linalg.expm.html); Al-Mohy/Higham (2009), [DOI:10.1137/09074721X](https://doi.org/10.1137/09074721X). | Reviewed official documentation of the installed existing dependency and its stated scaling/squaring reference. The augmented PWL derivation is original; analytical RC/RLC cases independently check physical trajectories. | No fresh full-text audit or own implementation of the library's Padé method is claimed. An expm-to-expm comparison alone is insufficient verification. |

The positive-real power-wave convention follows the explicitly defined existing
[network mathematics](INDUCTIVE_NETWORK_TRANSIENT.md); complex-reference support
is not inferred. Numerical/reference checks and independent review precede Done.
Knowledgeable human numerical review before release remains required.
