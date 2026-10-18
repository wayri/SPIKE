<!-- SPDX-License-Identifier: Apache-2.0 -->
# Integrated RLC work, resistor heat and boundary storage

SI07-S07 adds continuous energy integration to the
[initialized RLC transient](RLC_INITIAL_STATES.md). It observes the actual
propagated intervals and reuses the existing fitted model, mixed closure and
trajectory. The original public v1/v2 transient interfaces and results remain
unchanged. No second fit or separate electrical trajectory is needed.

This is a bounded experimental ledger for supplied series R/L and shunt C.
It does not infer physical dissipation/storage inside an arbitrary fitted
network or transfer heat to a thermal mesh. Full SI/PI parity remains open.

## API, quantities and provenance

Call `run_rlc_energy_ledger(request)` in
`python.spike_core.sparameter_rlc_energy`, or invoke that worker method with
exactly `params: {request: ...}`. The desktop script workspace can use the API;
no dedicated energy editor is added. Run the original free-decay example:

```powershell
.venv/Scripts/python.exe examples/rlc_energy_ledger/run_energy.py
```

`spike/rlc-energy-ledger-request/v1` requires `transient_request` in the existing
v2 contract, `relative_tolerance` (finite, >0 and <=1e-6), and
`absolute_tolerance_j` (finite and >0). These tolerances admit the energy-balance
residual, not the unknown physical device accuracy or a rigorous global
integration-error bound. They are retained in the result.

`spike/rlc-energy-ledger-result/v1` contains `transient_result`, the complete v2
result, a full-request digest, `intervals`, `totals` and numerical diagnostics.
Each interval has `start_time_s`, `end_time_s` and six source-port-ordered maps:

| Map | Physical meaning |
| --- | --- |
| `source_work_j_by_port` | Integral of Vs*Isrc; signed work delivered by the ideal source. |
| `network_work_j_by_port` | Integral of V*Inet; signed work entering the fitted network. |
| `resistor_heat_j_by_port` | Integral of supplied R*Isrc^2; nonnegative resistor heat. |
| `initial_boundary_storage_j_by_port` | Supplied L/C storage at interval start. |
| `final_boundary_storage_j_by_port` | Supplied L/C storage at interval end. |
| `balance_residual_j_by_port` | Source work minus network work, resistor heat and change in boundary storage. |

Totals use accurately summed work/heat, the first initial storage and last final
storage, not sums of endpoint storage. Their residual is recomputed and admitted.
All source knots and observations participate in the union interval grid.
Integration covers the full common source horizon even when the last requested
observation is earlier. `transient_result` retains source, boundary and initial
state identity; no implicit component/material/geometry model is added.

## Independently derived physical balance

With source current Isrc through R/L toward the port and Inet into the network,
the existing laws are Vs=V+R*Isrc+L*Isrc' and Isrc=Inet+C*V'. Multiply the first
by Isrc and substitute the second to obtain, for constant supplied R/L/C:

```text
Vs*Isrc - V*Inet = R*Isrc^2 + d(.5*L*Isrc^2+.5*C*V^2)/dt
Wsource - Wnetwork - Qresistor - (Efinal-Einitial) = 0
```

This identity holds per port and after summing ports. Initial energy must be
included for charged/energized states. Work entering the fitted network may
contain dissipation, physical storage change or active-source exchange; it is
not automatically heat. Generic fitted-state energy remains unspecified.

## Continuous quadratic integration

The connected normalized state satisfies z'=A*z+F*u, z=[x,q,v], with q=sqrt(Z)I
and v=V/sqrt(Z). On a PWL interval of duration h introduce y=[z,u,delta_u],
delta_u=u1-u0, and the dimensionless interval generator:

```text
G = [[h*A, h*F, 0], [0, 0, I], [0, 0, 0]]
y(tau)=exp(G*tau)*y0, 0<=tau<=1
```

All augmented coordinates have units sqrt(W). Physical quantities are linear
rows on y. For example a=Q*z+H*u, b=D*a+Cm*z, V=sqrt(Z)(a+b), and
Inet=(a-b)/sqrt(Z). On a dynamic port Vs=sqrt(Z)*u; on a pure-R port Vs=u/c,
where c=sqrt(Z)/(R+Z). Isrc=q/sqrt(Z) on L ports and follows the admitted
algebraic boundary on other ports. The resistor-power row is sqrt(R)*Isrc.

Normalize y0 by its L2 norm s, so B=(y0/s)(y0/s)^T has unit spectral norm when
y0 is nonzero. With the zero-seed case handled explicitly, define
J=integral(exp(G*t)*B*exp(G^T*t),t=0..1). Restore the seed scale in the physical
rows. The time integral of two physical outputs r*y and n*y is then
h*(s*r)*J*(s*n)^T. This integrates the continuous fitted-model trajectory;
it is not trapezoidal integration of sparse plotted samples.

To compute J without exponentiating an unstable block over the entire interval,
choose delta=2^-k so ||delta*G||2<=.5. For the small block exponential:

```text
exp([[delta*G, delta*B], [0, -delta*G^T]]) = [[E, X], [0, *]]
Jdelta = X*E^T
J2t = Jt + Et*Jt*Et^T; E2t = Et*Et
```

The off-diagonal block follows by differentiating the block exponential, and
multiplying it by E^T gives the covariance integral over [0,delta]. Splitting
the integral at t proves the doubling identity. Repeated doubling reaches 1.
This is the covariance orientation of the classical block-integral relation;
no custom Padé implementation or imported source code is used.

Check finite values, relative symmetry, positive-semidefinite admission and the
independent integral identity G*J+J*G^T=E*B*E^T-B. Symmetry and identity relative
residuals must be <=1e-10; the symmetric part is inspected for eigenvalue
admission but the returned Gramian is not symmetrized or projected. Negative
computed resistor heat rejects; it is never clipped. Raw balances remain in
the result, without redistributing residuals into work or storage.

For each interval and the totals require
abs(residual)<=absolute_tolerance_j+relative_tolerance*scale, where scale is the
sum of absolute source/network work, heat and endpoint storages. This admits
floating-point energy consistency; it cannot prove physical model accuracy or
replace independent analytic integration references. Diagnostics retain maximum
absolute/relative balance, Gramian identity/symmetry residuals, doubling count,
interval count and estimated aggregate work.

## Admission and future multiphysics use

The full request/result limits are 8/16 MiB. Existing trajectory limits, including
32 states, augmented dimension 48, 1,024 intervals and 128 unique durations,
remain. The covariance block dimension is at most 96. Charge each interval's
block exponential and doubling steps against the combined 100-million estimated
work limit; the covariance seed depends on that interval's state, so its block
exponential is not cached by duration alone. Preflight precedes ledger integrals,
after bounded model fitting/closure. Cancellation polls include blocks and folds.
Unsupported conditioning, precision/range, work, positivity, residual or
cancellation returns no successful partial ledger or trajectory.

Source identity, physical port/component ownership, interval boundaries and
resistor joules can support a later conservative thermal handoff. If converted
to interval-average heating, Q/h conserves that interval's heat but not its
within-interval temporal shape. Thermal mesh/material ownership, deposition,
time-grid transfer, temperature feedback and no-double-counting need separate
contracts. Do not add network work or L/C energy changes to resistor heating.
Changing L/C between runs also needs parameter-work accounting.

Stable active fits remain possible; signed work is intentional. No physical
fit-band extrapolation, generic internal-network dissipation/storage, managed
co-simulation, nonlinear/DAE or measured qualification is established. Existing
floating-point stability admission is not a robust certificate for arbitrary
nonnormal or uncertain models.

## Reviewed primary references and provenance

Reviewed 18 October 2026. The physical row construction, ledger, block/covariance
derivation, scaling and test fixtures are independently authored. No external
program, routine, figure, table or fixture was copied or translated. The
[numerical evidence policy](NUMERICAL_METHOD_EVIDENCE.md) applies.

| Source | Actual reviewed locator/use | Limits |
| --- | --- | --- |
| Charles F. Van Loan (1978), *Computing Integrals Involving the Matrix Exponential*, IEEE Transactions on Automatic Control 23(3), 395-404, [DOI:10.1109/TAC.1978.1101743](https://doi.org/10.1109/TAC.1978.1101743); [published-paper scan reviewed](https://www.olemartin.no/artikler/vanloan.pdf). | Mathematical sections II-III, pp.395-397: Theorem 1/block integral relation and equations (2.2), (3.5), (3.7), including covariance/observability orientation and doubling. Independently derive the particular trajectory covariance and physical work rows above. | No external Fortran source reviewed or adopted; no whole-paper error-analysis audit or claim that its error bounds automatically qualify this implementation. |
| David H. Staelin, *Electromagnetics and Applications*, copyright 2011, [MIT OCW-hosted text](https://live.ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/d3be4ea78b036a6362230fb41780cf54_MIT6_013S09_notes.pdf). | Sections 3.1.3/3.2.3: capacitor energy (3.1.16) and inductor power-to-energy relation (3.2.23); KVL/KCL locators retained in the parent method. | Ideal constant lumped components, not general material loss or physical fitted-state energy reconstruction. |
| SciPy 1.17.0 [`scipy.linalg.expm` Notes/References](https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.linalg.expm.html). | Official documentation for the existing exponential dependency reviewed. | Library algorithm lineage is distinct from this ledger's independent derivation and verification. |

Independent review and numerical checks precede Done. Knowledgeable human
numerical review before release and independent physical validation remain
required; synthetic correctness does not establish production qualification.
