<!-- SPDX-License-Identifier: Apache-2.0 -->
# Supplied ideal RLGC star junction: SI02-S06

Experimental, production-unqualified. Two through eight supplied scalar RLGC
legs meet at one ideal electrical node. Every leg's left terminal is an external
port; every right terminal meets the node. The returned multiport network and
coherent fields include repeated reflections and separately owned conductor and
dielectric heat. Existing [S03 networks](RLGC_LINE_NETWORK.md) and
[S04 fields](RLGC_LINE_FIELDS.md) execute unchanged.

This adds coherent interior fields and a conservative distributed-loss ledger
to a bounded branched line study. Generic supplied branched topology already
exists in the harness MTL subsystem; this stage does not establish new physical
junction or whole-board extraction capability.

## Reviewed source and original derivation

Reviewed 19 October 2026: David H. Staelin, *Electromagnetics and Applications*
(2011), chapter 8, section 8.1.2, printed pages 232 and 234: multiple-line
junctions and interface voltage/current continuity. Section 8.3.1, printed
pages 249–251, equations 8.3.3–4, 8.3.7–9 and 8.3.16: phasor telegrapher
equations, voltage/current propagation and dissipation.
[Official MIT full text](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf).
The mathematical sections were reviewed directly. Derivation, implementation,
fixtures and test oracles are independently authored; no external code,
figures, example data or implementation was copied or adapted.

Let r be the common positive real reference impedance [ohm]. The RMS power
waves a and b have units sqrt(W); a enters a leg and b leaves it. Terminal
voltage and current into that leg satisfy

```
V = sqrt(r)*(a+b)                 [V RMS]
I_into = (a-b)/sqrt(r)            [A RMS]
P_into = Re(V*conj(I_into)) = |a|²-|b|²   [W]
```

All m right-terminal voltages equal Vj, and the currents into the legs sum
to zero. Substitute a_k=Vj/sqrt(r)-b_k into the current sum to obtain
Vj/sqrt(r)=2*sum(b_k)/m. Hence the independently derived junction law is

```
a_right = J*b_right
J = (2/m)*ones(m,m)-identity(m)
J.T = J; J.T*J = identity(m)
```

The common-voltage subspace has eigenvalue +1; orthogonal differential
subspaces have eigenvalue -1. Orthogonality preserves summed wave power.
The ideal node stores no energy and produces no heat. At m=2 this is a swap,
recovering the cascade connection after reversing the second leg's spatial
orientation. Characteristic impedances may differ; r is only the common wave
coordinate. There is no inferred renormalization.

Let W be the block diagonal matrix of actual S03 two-port matrices. Let C
contain J on the right-terminal indices and zero elsewhere; U injects the m
external waves into left-terminal indices. Solve

```
b = W*a; a = C*b+U*a_external
(I-C*W)*X = U
S_external = select_left(W*X)
a_local = X*a_external
```

Both the m basis solves and coherent solve residual are checked. Actual S04
field requests receive each leg's local incident pair. Production does not
multiply growing spatial transfer matrices; the independent moderate-condition
test oracle uses those matrices with physical voltage/current constraints.

## Electrical conservation and multiphysics ownership

Each child retains its source request and digest, network, boundary fields,
probe V/I, nominal average electric/magnetic storage [J/m], transported power
[W], local losses [W/m] and integrated conductor/dielectric loss [W]. Child
identity, network, boundary fields versus connected waves and loss balances
are checked before returning the parent result.

With RMS phasors, the telegrapher equations imply

```
d Re(V*conj(I))/dx = -R*|I|²-G*|V|²
P_heat,leg = integral(R*|I|²+G*|V|²) dx
P_external = ||a_external||²-||S_external*a_external||²
global residual = P_external-sum(P_heat,leg)
```

Staelin's peak-phasor dissipation has a factor 1/2; RMS magnitudes here absorb
that factor. Child nominal storage remains .5*C*|V|² and .5*L*|I|². This is
effective nondispersive circuit storage, not general dispersive-material energy.
Sampled R/G may vary with frequency; causality is not established.

The parent retains each right-terminal voltage minus the first leg's actual
right voltage, the sum of inward currents, and the signed sum of right-terminal
powers. No common voltage is averaged or repaired. Branch currents need not
oppose pairwise: their sum is the constraint. External terminal powers are
checked against the independent external wave-power calculation. Each leg's
conductor/dielectric heat is counted once. Internal transported watts are not
heat. No clipping, passivity repair or residual redistribution occurs.

Each frequency is a separate coherent operating case. No sweep-wide sum of
watts or automatic thermal deposition is performed. Spatial ownership is by
leg and probe fraction, not inferred PCB copper/thermal cells.

## Wire contract and executable entry points

Python API: `run_rlgc_line_junction(request, *, cancel_check=None)`;
atomic errors are `RLGCLineJunctionError` with `RLGC_LINE_JUNCTION_*` codes.
Worker method: `run_rlgc_line_junction`, params `{request: ...}`.
Strict versioned schemas are
`schemas/rlgc-line-junction-request-v1.schema.json` and
`schemas/rlgc-line-junction-result-v1.schema.json`.

Request `spike/rlgc-line-junction-request/v1` has exactly:

- `legs`: 2–8 `{id,line_request,probes}` records. IDs are unique nonblank strings
  of at most 80 characters and define the external port names and order.
- `excitations`: `{frequency_hz,incident_waves}` records, where the vector has
  exactly one `{real,imag}` RMS incident wave per ordered leg.

Each line request obeys S03, with strictly positive frequencies for this
stage. Every leg and excitation must have exactly the same increasing grid;
every line reference must agree exactly. Each leg has 1–32 unique S04 probes.
All numeric inputs are finite nonboolean scalars. No extra fields are admitted.
Length, L, C and reference are positive; R and G are nonnegative.

The result has contract `spike/rlgc-line-junction-result/v1`, experimental
status, `production_qualified:false`, immutable source snapshot/digest, the
compatible m-port sampled `network`, ordered `legs:[{id,result:<S04>}]`, and
per-frequency `points`. Each point has `power_balance` (net input, conductor,
dielectric, total loss and raw residual watts) and `junction` (ordered complex
`voltage_residuals_v`, complex `current_residual_a`, signed `power_residual_w`).
Diagnostics report sample/leg counts, maximum absolute global/junction power
residuals, maximum voltage/current residual magnitudes and maximum connection
condition number. Limitations are included in every result.

```powershell
.venv/Scripts/python.exe examples/rlgc_line_junction/run_line.py
.venv/Scripts/python.exe -m python.spike_core.cli --quiet --output build/rlgc-junction.json rlgc-junction examples/rlgc_line_junction/three-legs.request.json
.venv/Scripts/python.exe -m unittest tests.python.test_rlgc_line_junction tests.python.test_rlgc_line_junction_contract -v
```

## Numerical admission and resources

Connection condition number must be finite and at most 1e8. The raw solve
residual norm is at most 1e-10 times
`norm(A)*norm(solution)+norm(rhs)`. External S is reciprocal within 1e-10 and
its largest singular value is at most 1+1e-9. These checks do not alter S.

Junction voltage residuals use relative tolerance 1e-9 against the maximum
terminal voltage magnitude and `sqrt(r)*sqrt(total incident power)`. The
current sum uses 1e-9 against summed current magnitudes and
`sqrt(total incident power)/sqrt(r)`. Power checks use 1e-10 against incident,
absolute transported or heat power as appropriate; there is no absolute floor.
Child boundaries use the same field tolerances against solved incident and
outgoing waves. Raw residuals remain in the result.

Limits: 1024 frequencies, 8 MiB finite JSON input and 16 MiB complete output.
Before any leaf solve, for input bytes B, samples n, legs m and total probes p:

```
predicted output = 5*B+n*(4096+4096*m+256*m²+1536*p)+65536 <= 16 MiB
estimated work = n*((2*m)³+8*m³+64*m+32*p) <= 100,000,000
```

The final serialized result is also bounded. Cooperative cancellation is
polled in validation, leaf construction, frequency solves, child fields and
final ledgers. Callback exceptions fail atomically. Floating overflow,
underflow, division and invalid arithmetic fail closed where reported by the
numerical runtime; finite results and residuals are also checked. Existing
S03/S04 propagation and representability limits apply unchanged. This is
ordinary floating-point accuracy, not an arbitrary-precision guarantee for
every tiny reflection beneath the numerical scale of other quantities.

## Executed verification and remaining validation

The supplied three-leg example is checked against an independent physical
nodal system: unknown left V/I states, `expm(-M*length)` on every leg,
external `V+r*I=2*sqrt(r)*a`, equality of right voltages and sum of right
spatial currents zero. Interior probes use independent spatial exponentials;
distributed loss uses independent adaptive quadrature.

On 19 October 2026, three network samples, 27 field probes and nine pairs of
owned heat integrals gave maximum absolute discrepancies:

| Observable | Maximum error |
|---|---:|
| Complex S element | 6.238e-16 |
| Voltage | 5.025e-15 V |
| Current | 1.571e-16 A |
| Conductor heat | 1.215e-17 W |
| Dielectric heat | 2.169e-18 W |

Acceptance uses 2e-12 absolute plus 1e-10 relative for S/fields/heat; storage
densities use 1e-20 J/m absolute. Independent trapezoid integration with
16/32/64 cells gave errors 1.220024e-6, 3.046293e-7 and 7.613385e-8 W,
approximately fourfold reductions. The example maximum global power residual
was 6.280e-16 W; junction voltage/current/power residuals were at most
3.383e-15 V, 1.186e-16 A and 1.222e-15 W.

Additional tests cover the analytic phased matched three-port result
`D*((2/3)*ones-I)*D`, eight-leg admission/unitarity, two-leg cascade equivalence
with reversed second orientation, coherent permutation/scaling, exact zero,
probe-independent integrated heat, and matched legs with attenuation 40 Np
each. The latter uses binary-exact matching to isolate very small propagation
from impedance roundoff. It checks S near exp(-80) at 2e-12 relative plus
1e-47 absolute, and analytic per-leg absorbed watts. Rejection tests cover
malformed identity/grids/references/probes/waves, output and work preflight,
cancellation, excessive condition, injected solve error, floating range and
corrupted child identity/boundaries/heat/residuals. Worker, CLI, example and
strict schema tests exercise the real registered path.

These are synthetic code/solution verification cases. There are no admitted
measurement comparisons or physical junction calibration data. No general
trees, loops, inferred stubs/loads, coupled conductors, actual return-path
transitions, launch/via/bend parasitics, board extraction, DC fields, transient
qualification or thermal deposition are claimed. Knowledgeable human review
remains required before release.
