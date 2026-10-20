<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S12: ideal coupled-line star junctions

Experimental development method,20 October2026. Connect2..8 supplied uniform
[symmetric coupled legs](RLGC_COUPLED_PAIR.md). All left endpoints are exterior;
all right endpoints with the same physical conductor identity meet at a common
ideal node. There are two distinct conductor nodes, not a short between the two
signal conductors. The reference conductor is implicit and shared. Exact
positive frequency grids, positive real port reference and physical conductor
identities/order must agree. Branch lengths and supplied modal RLGC may differ.
This is a bounded branched topology, not an arbitrary graph or geometric tee.

## Independent physical derivation

Use exp(j omega t) RMS phasors with V=sqrt(Z0)(a+b) and current into each leg
Iin=(a-b)/sqrt(Z0). At a common physical conductor node, all branch voltages
agree and sum Iin=0. For m legs, let every sum a_k+b_k be the same constant c.
Then a_k=c-b_k and sum a=sum b, hence c=2 sum(b)/m and

```
a = J b, J = (2/m) ones(m,m) - identity
```

The rank-one projector H=ones/m obeys H^2=H, so J=2H-I is real symmetric and
J.T J=I. Thus the ideal node stores/dissipates no energy and conserves signed
power. Place J separately on the right-port index set of each physical conductor.
Do not mix the two conductor nodes. Let B be block diagonal4by4 leg scattering,
C this internal node connection, and E inject2m exterior waves onto left ports.
The unchanged [conditioned connection solver](RLGC_COUPLED_CASCADE.md) solves
(identity-CB)X=E and S=E.T B X. Actual local drives X aext then execute each
unchanged S07 producer; the strong S08 binding checks requests/digests/modal and
physical fields and individual loss splits before retaining them.

External order is leg0-conductor0,leg0-conductor1,leg1-conductor0,... . Matrix
entries use S[receiver,source]. Network port labels are canonical UTF-8 JSON
encodings of [leg_id,conductor_id], so delimiters or Unicode in IDs cannot
silently alias different physical ports. Structured boundary records also retain
the original leg and conductor IDs. References and frequency grids are never
silently converted, interpolated, sorted or extrapolated.

## Energy, units and multiphysics boundary

Physical leg equations dV/dx=-(R+j omega L)I and dI/dx=-(G+j omega C)V retain
R/L/G/C in ohm/m,H/m,S/m,F/m. I inside a leg points from its exterior left end
toward its node; the right inward port current is its negative. Heat per leg is
integral(I^H R I+V^H G V)dx in W. Global net real exterior input equals the sum
of actual leg conductor and dielectric heat, counted once. Nested modal losses
are retained as evidence and are not added again. At each conductor node return
raw voltage mismatch per leg, summed inward current and signed power residual;
residuals are not relabeled as heat or redistributed to branches.

Stable leg IDs preserve an explicit future electrical/thermal ownership boundary.
Mutual terms remain pair-level quantities with no inferred individual-conductor,
contact-area or thermal-cell allocation. Child stored-energy densities remain
J/m; they are not added to heat W. Each sampled positive frequency is an
independent RMS steady scenario, without automatic summation or transient thermal
history. No junction contact/thermal material, heat deposition or temperature
feedback is constructed by this ideal model.

## Exact sources and clean-room provenance

D.H.Staelin, *Electromagnetics and Applications*, MIT online text(2011),
[official chapter8 PDF](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf).
Full text reviewed20 October2026: section8.1.2 printedpp232-234, especially
p234 physical V/I continuity, and section8.3.1 eqs8.3.1-8.3.9 pp249-250 and
eq8.3.16 p251 for complex line laws/dissipation as reviewed in constituent
stages. SPIKE's multi-leg KCL extension, projector proof, block connection,
RMS conversion, implementation and verification were independently authored in
project notation. The source's peak-phasor loss factor1/2 becomes unity for RMS
phasors. Common-node KCL and ideal wires are explicit lumped-circuit assumptions;
this source does not validate a real high-frequency geometric branch.
No external implementation, code, prose, figure, mesh, model or dataset was
copied, translated or adapted. References establish mathematical lineage,
not imported rights or experimental validation. New SPIKE-owned material is
Apache-2.0; no dependency, language or native PDE kernel is added.

## Numerical analysis and acceptance

Admit2..8 legs,4..16 exterior ports,1..1024 positive exact-grid samples and
1..32 probes/leg. Input<=8MiB and output<=32MiB; conservative combined preflight,
actual streamed retained/final sizes and100million dense connection-work units
bound work. Dense order<=32 with at most16 right-hand sides. Reuse direct solves,
condition<=1e8, residual<=1e-10*(norm(system)norm(X)+norm(E)), finite4by4 leg
matrices, actual SVD passivity<=1+1e-9 and reciprocity tolerance1e-9. No matrix
inverse, transfer-matrix growth, regularization, clipping or residual repair.
Exterior field agreement/node voltage/KCL tolerance1e-9 scaled norm; global heat
and per-node signed power tolerance1e-10 scaled power. Raw condition and residuals
are retained, not presented as physical uncertainty estimates. Nonfinite or
unrepresentable arithmetic, underflow/overflow, malformed/unsupported inputs,
cancellation or callback failure reject atomically with no successful partial
result. Poll during admission, propagation, sample solves, child execution/binding
and point assembly. Existing supplied modal line applicability limits remain.

No new time/space discretization is introduced. Frozen V/I/S tolerance2e-11
absolute plus2e-9 relative; heat/power2e-12 W absolute plus2e-9 relative.
The independent oracle assembles physical self/mutual telegrapher matrices for
each leg and solves a4m boundary system:2m exterior V+Z0I constraints,
2(m-1) equal-node-voltage constraints and2 node-KCL constraints. It uses matrix
exponentials without the production modal basis or wave node/connection helpers.
Every S column and coherent probe field is verified. Independent physical
quadratic32/64-node Gauss integration verifies each leg's conductor/dielectric
loss separately and confirms reference quadrature refinement.

Closed-form identical uncoupled matched legs give
S=exp(-2j beta length)*(2/m ones-I) tensor identity(2). Two legs reduce to the
unchanged piecewise coupled cascade network. Leg/conductor permutation,
zero/scaling, collision-free IDs and the actual8-leg16-port upper boundary pass.
Malformed identity/reference/grid/excitation, resources, trapped singular
connections,1e308 representability, cancellation/callback and forged child
identity/interior fields/total-preserving loss splits reject. Actual worker,
CLI, saved example, strict schemas, review and source-bound execution support
[validation](validation/SI02_COUPLED_STAR_20261020.md).

General graphs/asymmetric or changing modal bases, piecewise legs, physical RLC
terminal closure on the star, geometric junction/contact/return parasitics,
DC/transient/causal initialization, radiation, thermal allocation/feedback,
measurements and original-board qualification remain separate open stages.
Human numerical review remains required before release. This bounded stage
does not establish complete PI/SI or multiphysics parity.
