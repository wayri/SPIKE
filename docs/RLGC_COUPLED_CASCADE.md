<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S10: supplied piecewise symmetric coupled-line cascades

Experimental development method, 20 October 2026. Connect one to eight supplied
[symmetric co-directed pairs](RLGC_COUPLED_PAIR.md) in physical conductor order.
Each uniform section may have different supplied even/odd RLGC and length.
Exact positive frequency grids, conductor IDs/order and one positive real port
reference must agree across all sections. Interfaces are ideal, zero length,
with no explicit source, loss, shunt or stored energy. This introduces piecewise
coupled propagation and internal fields; geometry-derived discontinuities and
asymmetric/noncommuting matrix media are separate open problems.

## Independently authored connection derivation

Use exp(j omega t) RMS phasors, physical port order conductor0-left,
conductor1-left, conductor0-right, conductor1-right. Voltage is relative to the
shared reference conductor; port current enters its own section. Inside each
section field current points left to right. The unchanged producer uses
V = sqrt(Z0)(a+b), Iin = (a-b)/sqrt(Z0) with waves in sqrt(W).
At a connected physical conductor, voltage continuity and opposing inward
currents give a_left+b_left = a_right+b_right and
a_left-b_left = -(a_right-b_right), hence a_left=b_right and
a_right=b_left. These are componentwise physical connections, without modal
renormalization or assumed impedance matching between sections.

Let B be block diagonal section scattering, P the symmetric permutation of only
internally connected ports, and E inject four exterior waves into the first left
and last right ports. Then b=B a and a=P b+E aext. Solve

```
H X = E, H = identity - P B
Sext = E.T B X
asection = X aext
```

Direct solves retain reflections at every interface. The code does not multiply
exponentially growing transfer matrices, invert H explicitly, clip singular
values or regularize singular connections. All samples and matrix entries retain
S[receiver,source] order. Actual solved incident waves drive each unchanged S07
section producer. Its complete request/digest/modal results/physical fields and
individual conductor/dielectric loss splits are checked with the existing strong
S08 binding before they can contribute to a result. Repeated section model IDs
are forbidden; input order defines physical topology.

## Power, heat ownership and multiphysics boundary

RMS transported real power is Re(V dot conj(I)). The summed inward work at an
ideal interface is zero because voltage agrees and currents oppose. For a passive
section, integrated pair conductor heat is integral I^H R I dx and dielectric
heat is integral V^H G V dx, with R in ohm/m and G in S/m. Their sum is heat W.
Global real input is abs(aext)^2-abs(bext)^2, equal to the sum of section heat.
Only section losses are counted once; interface transfers and nested modal
results are retained for provenance, never added again as dissipation. Lossless
reactive storage remains within child field outputs in J/m and is not heat.

Stable section and conductor identities permit later explicit physical thermal
mapping. This method does not allocate mutual terms to individual conductors,
construct thermal cells, infer finite contact areas or impose temperature laws.
Each frequency is an independent steady operating scenario; sample losses must
not be automatically summed or used as transient thermal histories.

## Sources, exact review and rights

D. H. Staelin, *Electromagnetics and Applications*, MIT online text (2011),
[official chapter 8 PDF](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf).
Full text reviewed 20 October 2026: section8.1.2, printedpp232-234, especially
p234 physical voltage/current continuity between lines; section8.3.1,
eqs8.3.1-8.3.9 printedpp249-250 for lossy complex telegrapher laws and
eq8.3.16 p251 for distributed dissipation. These are physical foundations;
SPIKE's multiport permutation solve, RMS conventions, derivation, data structures,
code, fixtures and independent physical-chain oracle were authored independently.
The source's peak-phasor loss factor1/2 becomes unity with RMS phasors. Existing
coupled-pair modal references and their exact scope remain in the S07 method.
No external implementation, prose, figures, dataset, model or test was copied,
translated or adapted. References establish lineage and applicability, not
implementation redistribution rights or physical validation. New SPIKE-owned
material is Apache-2.0; no dependency or implementation language is added.

## Numerical analysis, limits and failures

Admit1..8 sections,1..1024 positive exact-grid samples and1..32 probes/section
within8MiB input and32MiB result. A conservative nested-result estimate, actual
streamed sizes and100million estimated dense connection-work units bound work.
The largest connection system is32 by32, with four right-hand sides. Check
condition <=1e8 and raw solve residual <=1e-10 times norm(H)norm(X)+norm(E).
Admitted section scattering must be finite4by4. Composite passivity uses actual
SVD with largest singular value <=1+1e-9; reciprocity tolerance1e-9. No clipping.
Exterior field agreement and interface voltage/current residuals use1e-9 norm
scales. Interface power cancellation and global heat balance use1e-10 physical
power scales. Raw condition/residuals are returned; residuals are not redistributed.
Underflow, overflow, invalid arithmetic, singularity or unrepresentable output
fail atomically, as do cancellation and callback exceptions. Poll at admission,
bare propagation, sample solves, child execution/binding and output assembly.
No successful partial field is returned on error. Child propagation/physical
applicability limits remain in force; huge model coefficients do not become
physically validated merely because a conditioned solve succeeds.

There is no new time or spatial discretization in this boundary connection.
Homogeneous section subdivision must leave S and total heat unchanged, while
physical-field quadrature is separately checked at32 and64 nodes. Sample-grid
refinement is not evidence of broadband causality or measured predictive accuracy.

## Frozen acceptance and executed evidence

Pre-implementation tolerance: V/I and scattering2e-11 absolute plus2e-9 relative;
heat2e-12 W absolute plus2e-9 relative. A separate physical four-state solver
constructs self/mutual R/L/G/C matrices, chains SciPy spatial exponentials, and
solves exterior V +/- Z0 I conditions. It uses no production wave connection,
modal basis matrix or propagation helper. It verifies every S column and coherent
section probe fields. Independent physical quadratic32/64-node quadrature
verifies each section's conductor/dielectric heat independently of total balance.
One-section identity, homogeneous subdivision, uncoupled scalar-cascade reduction,
zero/scaling, conductor permutation and chain reversal test limiting behavior.
Malformed fields/IDs/references/grids, work/output limits, singular/nonfinite
connections, cancellation/callback exceptions, forged identity/interior fields
and total-preserving false loss splits test failure behavior. Worker/CLI, saved
example, strict nested schemas, source-bound receipt, review and genuine affected
prior replays complete development verification.

[Executed validation](validation/SI02_COUPLED_CASCADE_20261020.md) records results.
No original board or measurement qualification, material extraction, physical
bend/via/launch/return impedance, branching, general matrix basis, causal/transient
initialization, nonlinear endpoint, radiation, thermal deposition or coupled
feedback is established. Numerical human review remains required before release.
