<!-- SPDX-License-Identifier: Apache-2.0 -->
# Combined R/L source and shunt-C fitted-network transients

SI07-S05 combines the supplied [series-inductive](INDUCTIVE_NETWORK_TRANSIENT.md)
and [shunt-capacitive](CAPACITIVE_NETWORK_TRANSIENT.md) source/load models in one
calculation. Its topology is an ideal voltage source followed by series R and L,
then a network port with C shunted to its reference node. Component values are
supplied lumped parameters; this does not extract package or PCB geometry.

The bounded model is experimental, zero-initial-state, linear and time invariant.
General circuit topology, descriptor/DAE, nonlinear receivers, arbitrary initial
states, measured broadband qualification and thermal integration remain open.

## Workflow and contract

Call `run_rlc_network_transient(request)` from
`python.spike_core.sparameter_rlc_terminated`, or invoke the same worker method
with exactly `params: {request: ...}`. The desktop script workspace can use this
API; no dedicated boundary editor is added. Execute the original example:

```powershell
.venv/Scripts/python.exe examples/rlc_network_transient/run_loaded_rlc.py
```

`spike/rlc-network-transient-request/v1` requires `fit_request`, `terminations`
and `output_times_s`. Each termination has exactly `port_name`, `resistance_ohm`,
`inductance_h`, `capacitance_f`, and continuous PWL `voltage_points` with `time_s`
and `voltage_v`. R/L/C must be finite and nonnegative. At least one positive L
and one positive C are required across the request; they may belong to the same
port or different ports. When C>0 and L=0, R must be positive. An L>0 port may
have R=0 if the complete connected model passes resolved stability admission.
Zero source voltage represents a load. Missing loads are not inferred.

Every source port must have one termination; request order does not change source
port order. All waveforms start at zero, share a positive horizon, and cover every
requested output time. Fitted memory, inductor currents and capacitor voltages
initially vanish. Output times are finite, strictly increasing and inside the
common horizon. The actual supplied-pole fitter executes; original source,
boundaries, digest and fit result remain in the derived result.

`spike/rlc-network-transient-result/v1` returns source/network currents separately,
network voltage, incident/outgoing waves, capacitor voltages/derivatives, inductor
currents/derivatives, both physical residuals, supplied resistor loss and component
energies. L/C-only maps and final values use `inductive_port_names` and
`capacitive_port_names`, each a source-ordered subset. `final_state_sqrt_w`
contains fitted memory only. These are histories, not a resumable session.

## Independently derived mathematics

Let Z be the common positive real reference impedance, a/b instantaneous
power-normalized incident/outgoing waves in sqrt(W), and Inet point into the
modeled network. Then V=sqrt(Z)(a+b), Inet=(a-b)/sqrt(Z). Isrc flows through the
series R/L branch toward the port. The component laws give:

```text
Vs = V + R Isrc + L dIsrc/dt
Isrc = Inet + C dV/dt
```

For fitted memory x, b=D a+Cm x and x'=Ap x+Bp a. Append q=sqrt(Z) Isrc
for positive-L ports and v=V/sqrt(Z) for positive-C ports, in source order, to
form z=[x,q,v]. All coordinates have units sqrt(W). At each port choose one
algebraic row, with C taking precedence when both elements are present:

| Boundary | Algebraic row |
| --- | --- |
| C>0, with or without L | (I+D) a = v-Cm x |
| C=0, L>0 | (I-D) a = Cm x+q |
| C=L=0 | (I-Gamma D) a = Gamma Cm x+c Vs |

Here Gamma=(R-Z)/(R+Z), c=sqrt(Z)/(R+Z). A regular conditioned solve of the
stacked mixed rows gives a=Q z+H u. On dynamic ports u=Vs/sqrt(Z); on pure-R
ports u=c Vs. Define beta=1/(Z C), alpha=1/(R C) when used. Physical dynamics are:

| Positive elements | Additional state equations |
| --- | --- |
| L and C | q'=(Z/L)(u-v)-(R/L)q; v'=beta(q+v-2a) |
| L only | q'=(Z/L)u+((Z-R)/L)q-2(Z/L)a |
| C only | v'=alpha u+(beta-alpha)v-2 beta a |

Substitute the solved a into these rows and the fitted-memory equation to obtain
z'=A z+F u. No numerical differentiation of reported histories is needed.
For each interval h with continuous linear input from u0 to u1, use the
dimensionless augmented system on [z,u,delta_u]:

```text
G = [[h A, h F, 0], [0, 0, I], [0, 0, 0]]
[z1, *, *] = exp(G) [z0, u0, u1-u0]
```

This is exact PWL integration of the admitted fitted model up to floating-point
arithmetic, not exact integration of the physical device represented by samples.
Insert every source knot and observation into the interval grid. Grid refinement
checks this propagation; it cannot establish missing broadband source accuracy.

### Independent physical references and power

For a supplied resistor network with scalar conductance Gload and both L/C,
eliminate Isrc to obtain an independent second-order voltage equation:

```text
L C V'' + (R C+L Gload) V' + (1+R Gload) V = Vs
V(0)=V'(0)=0; Isrc=C V'+Gload V
```

Analytic under/critical/overdamped solutions check both states and derivatives.
For a coupled conductance matrix, directly integrate
Ldiag Isrc'=Vs-Rdiag Isrc-V and Cdiag V'=Isrc-Gload V. These physical coordinates
and equations are separate from fitted wave closure. Comparison with existing
R/RL/RC APIs checks mixed-boundary reductions, alongside independent references.

A third-order reference makes fitted memory nonzero: place conductance Gload in
parallel with a physical inductor Ln inside the modeled network. Then
Inet=Gload V+In, In'=V/Ln, C V'=Isrc-Gload V-In and
L Isrc'=Vs-R Isrc-V. Its scattering model has
D=(1-Z Gload)/(1+Z Gload), p=Z/[Ln(1+Z Gload)] and normalized residue
-2/(1+Z Gload). Physical [V,Isrc,In] equations check the combined [x,q,v]
feedback path; constant-resistor fits alone would leave this path untested.

The instantaneous boundary power identity is:

```text
Vs Isrc - V Inet = R Isrc^2 + d(L Isrc^2/2+C V^2/2)/dt
```

For multiple ports, sum the identity. Reported resistor watts use Isrc, which
generally differs from Inet. Reported joules are only the supplied boundary
components' physical storage. Generic fit states have no inferred physical
stored energy or thermal ownership. Signed source work and network-port work
must remain distinct from resistor heating to avoid double counting.

Typed units, source/port identity, derivatives and loss/storage histories support
later conservative coupling. This stage does not integrate heat onto a thermal
mesh, apply temperature/material laws, reconstruct field energy, or implement a
steppable co-simulation interface. Those need separate ownership/transfer gates.

## Numerical admission and limitations

Require minimum mixed-row singular value >=1e-10*max(1,sigma_max), condition
<=1e10, and backward error <=1e-10. Require positive connected decay margin and
relative construction-scale margin >1e-10. These floating-point diagnostics are
not a robust-stability certificate for arbitrary nonnormal or uncertain models.
Stable active networks may pass; sampled passivity is not universally imposed.

Validate normalized physical KVL/KCL, mixed algebraic rows and L/C state
consistency, with finite precision and cancellation checks. Limits include
32 total states and augmented dimension 48, including every L and C state;
1,024 intervals/observations; 128 distinct durations; 100 million estimated work;
8 MiB request; 16 MiB result; dimensionless generator norm <=1e6. Unsupported
precision, singularity, unresolved/marginal stability, resources or cancellation
return no successful partial trajectory. Do not regularize or repair such input.

Some physically well-defined connections require constrained state elimination
or a descriptor solver and are rejected. Mutual boundary L/C, ideal voltage
sources directly on C-only ports, infinite/open loads, nonlinear/time-varying
elements, arbitrary topology and nonzero initial states are unsupported. This
does not complete SI07, SI/PI parity or physical broadband validation.

## Reviewed primary sources and provenance

Reviewed 18 October 2026. The mixed formulation, implementation and synthetic
fixtures are independently authored; no external code, diagram, deck or fixture
was copied. Follow the [method evidence policy](NUMERICAL_METHOD_EVIDENCE.md).

| Source | Actual reviewed locator/use | Limits |
| --- | --- | --- |
| David H. Staelin, *Electromagnetics and Applications*, copyright 2011, [MIT OCW-hosted text](https://live.ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/d3be4ea78b036a6362230fb41780cf54_MIT6_013S09_notes.pdf). | Sections 3.1.3, 3.2.1/3.2.3, 3.4.1 and 3.5.1: capacitor law/energy (3.1.12)/(3.1.16), inductor law (3.2.5), energy (3.2.23), KVL/KCL (3.4.1)/(3.4.3), RLC damping/energy discussion. Derive this topology and its loaded reference independently from those laws. | Ideal lumped constitutive laws; this text does not supply SPIKE's mixed wave-state algorithm or qualify sampled-network accuracy. |
| Installed SciPy 1.17.0 [`scipy.linalg.expm` Notes/References](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.linalg.expm.html), citing Al-Mohy/Higham (2009), [DOI:10.1137/09074721X](https://doi.org/10.1137/09074721X). | Official API/algorithm documentation reviewed for the existing dependency; independently derived PWL augmentation is checked with analytic circuit trajectories. | No fresh full-text paper audit or reimplementation of the library method is claimed. An expm-to-expm comparison alone is insufficient. |

The positive-real instantaneous power-wave convention is explicitly defined
above; unequal/complex reference impedances are not inferred. Independent review
and numerical checks precede Done. Knowledgeable human numerical review before
release and independent measurement validation remain required.
