<!-- SPDX-License-Identifier: Apache-2.0 -->
# Supplied RLC initial states and stateless continuation

SI07-S06 extends the [combined R/L and shunt-C model](RLC_NETWORK_TRANSIENT.md)
with explicit initial fitted memory, inductor current and capacitor voltage.
The original v1 API remains zero-state. The v2 adapter reuses the same admitted
mixed closure, propagation, observations and loss/storage calculation.

This is a bounded experimental initial-value problem and a way to pass its final
state into another call. It is not a managed co-simulation session, authenticated
checkpoint, arbitrary circuit/DAE solver or thermal coupling implementation.

## API and workflow

Call `run_initialized_rlc_network_transient(request)` from
`python.spike_core.sparameter_rlc_initial`, or invoke that worker method with
exactly `params: {request: ...}`. Run the original free-decay example:

```powershell
.venv/Scripts/python.exe examples/rlc_network_initial/run_free_decay.py
```

`spike/rlc-network-transient-request/v2` retains the v1 fit, terminations and
output times, adding a mandatory `initial_state`. The state contract is
`spike/rlc-initial-state/v1`, with exactly:

| Field | Meaning |
| --- | --- |
| `contract` | The state-contract identifier. |
| `fit_request_digest` | SHA-256 of canonical finite JSON for the entire `fit_request`: sorted keys, compact separators, UTF-8, no ASCII escaping. |
| `fit_state_sqrt_w` | K-by-N real fitted memory, in supplied pole order and source-port order. |
| `inductor_current_a_by_port` | Physical source-branch current at every positive-L port, no missing/extra ports. |
| `capacitor_voltage_v_by_port` | Physical voltage at every positive-C port, no missing/extra ports. |

Values may have either sign but must be finite real numbers, not booleans. Digest,
shape, port subsets and normalization are checked before actual fitting. The
digest binds source samples, reference, ordered ports/poles and fit options;
even a physically equivalent but differently encoded request can have a different
digest. The actual fitter executes for every call; there is no fit-cache claim.

`spike/rlc-network-transient-result/v2` retains the v1 observables and adds
`initial_state` (the exact supplied record) and `restart_state` (the final fitted
memory and physical component values in the same state contract). Its input
digest covers the entire v2 request. Fit/source/boundaries remain attached.

**The returned restart state is at the common source-waveform horizon, not
necessarily the last requested observation.** A state record contains no clock.
To reproduce an uninterrupted run across a split:

1. Trim every first-chunk source waveform to the split, interpolating its exact
   PWL value if the split is inside a ramp. Make that the common horizon.
2. Run the first chunk and copy its `restart_state` into the next `initial_state`.
3. Reslice every remaining waveform, subtracting the split time so it starts at
   local time zero with the same cut value. Keep subsequent knots and source
   horizon, and translate requested observations onto that local clock.
4. Keep the fit request and boundary topology/parameters identical for an
   uninterrupted-trajectory comparison. Translate returned times back explicitly.

The record authenticates neither its contents nor numerical-code revision. It
does not bind the boundary parameters, source history or absolute time. Changed
parameters/forcing are a separately specified initial-value problem; continuity
or conservative transfer across such changes is not established automatically.
Changing L/C also changes physical stored energy at fixed I/V and requires its
own work/energy accounting in a future coupling contract. A managed session will
need model revision, clock, accepted-step and rollback rules beyond this record.

## Independently derived initialization and continuation

The fitted realization uses x'=-p x+p a and b=D a+sum(Rk xk), with x and waves
in sqrt(W). A normalized mixed state is z=[x,q,v], q=sqrt(Z) Isrc on positive-L
ports and v=V/sqrt(Z) on positive-C ports, each subset in source order. Set z0
from the supplied record rather than to zero, then solve the same algebraic rows
and evaluate KVL/KCL to determine a0, b0 and state derivatives. Voltage/current
are not overwritten after algebraic closure. This requires a regular admitted
model; constrained/descriptor initial conditions are not projected or repaired.

For z'=A z+F u, the initial-value solution is
z(t)=exp(A t)z0+integral(exp(A(t-s))F u(s),s=0..t). The same dimensionless
augmented PWL exponential described in the parent method propagates arbitrary
finite z0. Uniqueness and composition of this linear initial-value solution give
the split-run identity when the cut state, local forcing, parameters and clock
translation are consistent. Split/refined runs verify that identity numerically.
No new timestep approximation or differentiation of output samples is introduced.

For a known resistor-load conductance G with both L/C, retain the physical
reference equation from SI07-S05:

```text
L C V''+(R C+L G) V'+(1+R G) V = Vs
V(0)=V0; V'(0)=(I0-G V0)/C; Isrc=C V'+G V
```

Its analytic free/forced damping solutions check charged/energized trajectories
and both derivatives. The known initial energy is .5*L*I0^2+.5*C*V0^2.
For the additional known G-parallel-Ln network, Inet=G V+In and In'=V/Ln.
With its rational D=(1-Z G)/(1+Z G) and residue=-2/(1+Z G), substitute wave
definitions to obtain In=2*x/sqrt(Z); hence x0=.5*sqrt(Z)*In0. This supplies an
independent physical nonzero-memory oracle, including initial .5*Ln*In0^2.
It is not an energy reconstruction for arbitrary fitted models.

The boundary power identity remains
Vs Isrc-V Inet=R Isrc^2+d(.5*L*Isrc^2+.5*C*V^2)/dt. Integrated energy tests
include initial storage: initial energy+source work=heat+final energy, with
known internal-network storage included only in the physical reference. Generic
fit-state energy remains unspecified. Source and network current, resistor heat,
electric/magnetic storage and signed work retain separate meanings and units.

## Numerical admission, coupling and limits

All v1 regularity, resolved-stability, precision, PWL, resource and cancellation
limits remain in force: 32 total states, augmented dimension 48 including L/C,
1,024 intervals/observations, 128 distinct durations, 100 million estimated work,
8 MiB full request, 16 MiB full result and generator norm <=1e6. Initial-state
unit conversion, finite trajectory and power/energy ranges must also be
representable. Failed initialization or cancellation returns no successful
partial trajectory. No state projection, clipping or repair is performed.

Physical initial I/V and returned typed state can support future coupled solver
handoffs. This does not validate temperature-dependent laws, physical fit-state
storage, integrated thermal transfer, time-varying components or arbitrary
state/model transformations. Stability admission remains a floating-point check,
not a robust certificate for arbitrary nonnormal or uncertain systems. Measured
broadband/passivity/causality qualification and full PI/SI parity remain open.

## Reviewed primary sources and provenance

Reviewed 18 October 2026. Derivation, code, examples and synthetic fixtures are
independently authored. No external source code, figures or fixtures are copied.
The [numerical evidence policy](NUMERICAL_METHOD_EVIDENCE.md) applies.

| Source | Actual reviewed locator/use | Limits |
| --- | --- | --- |
| David H. Staelin, *Electromagnetics and Applications*, copyright 2011, [MIT OCW-hosted text](https://live.ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/d3be4ea78b036a6362230fb41780cf54_MIT6_013S09_notes.pdf). | Section 3.5.1, equations (3.5.1)-(3.5.15) and initial-condition discussion following (3.5.9): component laws, exponential solutions and selecting amplitudes/phase from initial conditions. Capacitor/inductor energy and KVL/KCL locators are retained in the parent method's reviewed ledger. | Ideal lumped physical references; does not supply SPIKE's record protocol or qualify arbitrary fitted-state physical interpretation. |
| SciPy 1.17.0 [`scipy.linalg.expm` Notes/References](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.linalg.expm.html), citing Al-Mohy/Higham (2009), [DOI:10.1137/09074721X](https://doi.org/10.1137/09074721X). | Official documentation for the existing exponential dependency reviewed; reuse the parent PWL derivation with supplied z0. Separate analytic scalar cases check numerical trajectories. | No new full-text paper audit or library reimplementation claimed; shared-expm physical comparisons alone are insufficient verification. |

Independent review and numerical checks precede Done. Knowledgeable human
numerical review before release and independent physical validation remain
required; synthetic verification does not establish production qualification.
