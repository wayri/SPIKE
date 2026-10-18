<!-- SPDX-License-Identifier: Apache-2.0 -->
# Mixed resistive and series-inductive fitted-network transients

SI07-S03 extends [resistive Thevenin boundaries](TERMINATED_NETWORK_TRANSIENT.md)
with supplied series inductance at selected ports of an internally fitted
multiport model. It is a bounded experimental linear transient solver, not a
general circuit/DAE solver or a physical broadband qualification of sampled data.

## Contract and use

Call `run_inductive_network_transient(request)` in
`python.spike_core.sparameter_inductive_terminated`, or use the worker method
of the same name with exactly `params: {request: ...}`. The desktop script
workspace can invoke the API. No dedicated inductive-boundary editor is added.
The executable original example is:

```powershell
.venv/Scripts/python.exe examples/inductive_network_transient/run_rlc.py
```

`spike/inductive-network-transient-request/v1` contains `fit_request`,
`terminations` and `output_times_s`. Each port has exactly one termination:
`port_name`, `resistance_ohm`, `inductance_h` and continuous PWL `voltage_points`
(`time_s`, `voltage_v`). R and L are finite/nonnegative and at least one port
must have L>0. L=0 uses the resistive boundary; a zero voltage source is a load.
All sources start at zero time and share one positive horizon. Observation times
are explicit/strictly increasing and inside that horizon. Missing loads, infinite
impedances, nonzero initial conditions and waveform extension are not inferred.

The actual supplied-pole rational fitter executes, and the complete fit/source
and original boundaries remain in `spike/inductive-network-transient-result/v1`.
Source port ordering determines all maps and the separate `inductive_port_names`.
Results retain nodal port V/I and power waves, positive-L port inductor I/dI/dt,
boundary residuals, supplied resistor power and supplied inductor energy. Final
network pole states and final inductor currents remain explicit and separate.

## Governing physics and independent derivation

Current I is positive into the fitted network; source voltage is the Thevenin
voltage. Z0 is the common positive real reference impedance. With instantaneous
real power-normalized waves a,b in sqrt(W),

```text
V = sqrt(Z0) (a+b),    I = (a-b)/sqrt(Z0)
Vs = V + R I + L dI/dt
```

Use the existing fitted representation `b=D a+C x` and
`x_dot=A0 x+P a`, where C concatenates residue blocks, P stacks `pk I`,
and A0 has blocks `-pk I`. These are fitted-model states, not automatically
identified physical capacitor/inductor energies.

For every positive-L port introduce `q=sqrt(Z0) I=a-b`; q has the same sqrt(W)
units as x. Its algebraic row is `a-b=q`. A zero-L row instead has
`a-Gamma b=u`, with `Gamma=(R-Z0)/(R+Z0)` and
`u=sqrt(Z0)/(R+Z0) Vs`. For positive-L ports define `u=Vs/sqrt(Z0)`.

Let G be diagonal, with Gii=1 at positive-L ports and Gii=Gamma otherwise;
E selects positive-L ports from the full port list; B is diagonal with 1 on
zero-L ports and 0 elsewhere. The mixed algebraic problem is

```text
M = I - G D
M a = G C x + E q + B u
Qx = solve(M,G C),  Qq = solve(M,E),  H = solve(M,B)
a = Qx x + Qq q + H u
```

The inductor law independently gives, on its positive-L rows,

```text
q_dot = (Z0/L) [u_L - 2 a_L + (1-R/Z0) q]
```

Substitute the algebraic solution into x_dot and q_dot to obtain the full
constant linear state problem `z_dot=A z+F u`, z=[x,q]. No artificial resistor,
pseudoinverse or regularization repairs a singular closure. In particular some
physically meaningful circuits with singular direct-feedthrough current
constraints need a more general descriptor/DAE formulation and are rejected here.

PWL propagation uses a dimensionless augmented exponential on each union-grid
interval h, with state coordinates `[z,u,delta_u]` all in sqrt(W):

```text
generator = [[h A, h F, 0], [0,0,I], [0,0,0]]
[z_next,u_next,delta_u] = exp(generator) [z,u_start,u_end-u_start]
```

Transitions are cached by interval duration. This is exact evolution of the
admitted fitted LTI model up to floating-point computation; observation-grid
refinement does not repair the physical accuracy or bandwidth of that model.
Output times introduce no integration approximation. Waveform corners are
handled using continuous source values and the applicable state equation.

## Numerical admission and failure behavior

The algebraic closure must have smallest singular value at least
`1e-10*max(1,sigma_max)`, condition at most 1e10 and backward error at most 1e-10.
The complete connected matrix, including inductor states, must have strictly
negative eigenvalue real parts and a resolved relative stability margin above
1e-10 against its construction scale. This rejects unstable, marginal/lossless
and unresolved cases; a stable source fit alone is insufficient.

Finite values, source/time normalization, inductor-current consistency and
normalized KVL boundary residuals are checked. Limits include 32 total dynamic
states and augmented dimension 48 **including the added inductor states**,
1,024 intervals/output observations, 128 distinct durations, 100 million
estimated aggregate work, 8 MiB request and 16 MiB result. Dimensionless
exponential-generator norm is bounded by 1e6. Unsupported floating-point ranges,
including coefficient/energy collapse, fail explicitly. Cancellation is polled
around bounded fitting and algebra/exponential operations. No successful partial
trajectory is returned after failure or cancellation.

## Multiphysics interface and limits

Per-port `termination_resistor_power_w_by_port` is actual `R I²` for supplied
boundary resistors; `inductor_energy_j_by_port` is `.5 L I²` on positive-L ports.
Together with I/dI/dt and V they support the boundary identity
`Vs I = V I + R I² + L I dI/dt`. Sign, units, port identity, input digest and
the complete fit/boundary snapshots are preserved for later coupled studies.

These are instantaneous typed electrical outputs. This stage does not integrate
resistor heat into a thermal mesh, infer winding geometry/material/temperature
laws, expose a steppable co-simulation session or calculate mechanical forces.
Do not interpret fitted-network states as physical stored energy without a
separate realization/qualification. Capacitive/nonlinear/coupled termination
topologies, arbitrary initial states and marginal/descriptor systems remain open.
Fit-band extrapolation, measured causality/passivity and physical uncertainty
remain separate gates. All results are experimental and production-unqualified.

Eigenvalue/margin checks are floating-point admission diagnostics, not certified
robust stability for arbitrary nonnormal matrices or uncertain parameters.

## Method references and review extent

Reviewed 18 October 2026. Equations, implementation and synthetic test circuits
are independently authored; no external code, diagram or fixture is copied.

| Primary source | Reviewed extent and method use | Limits |
| --- | --- | --- |
| MIT OpenCourseWare, *18.03SC Differential Equations*, Fall 2011, *RLC Circuits*, [official notes](https://ocw.mit.edu/courses/18-03sc-differential-equations-fall-2011/035929616dc2553a2fee2aa787a96652_MIT18_03SCF11_s20_1text.pdf), pp.1–3, sections 1/3/4 and equations (1), (3), (5). | Reviewed constitutive V/I units, series-circuit KVL, second-order RLC form and electromechanical analogy. Independently derive the mixed wave closure and RLC references from these laws. | Classical ideal lumped R/L/C, not a reference for arbitrary sampled-network physical accuracy or multiphysics qualification. |
| SciPy 1.17.0, [`scipy.linalg.expm` Notes/References](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.linalg.expm.html). Al-Mohy/Higham (2009), *A New Scaling and Squaring Algorithm for the Matrix Exponential*, [DOI](https://doi.org/10.1137/09074721X). | Reviewed official API documentation for the installed dependency and its stated algorithm reference. The augmented PWL derivation is original; execution uses the existing SciPy dependency. | No claim of a fresh full-text audit or independent implementation of the library's Padé algorithm. Reference-circuit oracles must also include analytic formulas, not only another expm call. |
| Kurokawa (1965), *Power Waves and the Scattering Matrix*, [bibliographic DOI](https://doi.org/10.1109/TMTT.1965.1125964); existing [reference ledger](SOLVER_REFERENCES.md). | Existing convention provenance; the positive-real Z0 formulas are explicitly defined and independently used above. | DOI/full-text retrieval did not succeed in this review. Do not describe its equations/pages as freshly reviewed or infer complex-reference support. |

The [method evidence policy](NUMERICAL_METHOD_EVIDENCE.md) applies. Independent
analytic RLC step cases cover under/critical/overdamping; PWL and mixed-port cases
use independently derived physical circuit equations. Boundary/current/energy,
unit scaling, observation-grid, active/singular/stability and failure/resource
checks precede Done. Exact executed counts and source bindings belong to the
stage receipt, not to an inferred capability claim. Knowledgeable human numerical
review remains required before release.
