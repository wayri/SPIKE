<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S11: physical RLC endpoints for supplied coupled cascades

Experimental development method,20 October2026. This stage composes unchanged
[reactive physical endpoints](RLGC_REACTIVE_PAIR.md) and
[piecewise coupled propagation](RLGC_COUPLED_CASCADE.md). A complete four-port
Thevenin source/load assignment drives1..8 supplied symmetric co-directed line
sections. User inputs are physical complex RMS source voltages, positive series
R, ideal series L and ideal line-node-to-reference shunt C. Model sections retain
exact common positive frequency grids, real reference and physical conductor
identities/order. No contact geometry, thermal ownership, discontinuity
parasitics or additional constitutive model is inferred.

## Physical laws and independently derived composition

Let each section use dV/dx=-(R+j omega L)I and dI/dx=-(G+j omega C)V in
physical conductor coordinates. R/L/G/C here are distributed matrices in ohm/m,
H/m,S/m,F/m. RMS waves obey V=sqrt(Z0)(a+b), Iin=(a-b)/sqrt(Z0).
Ideal section interfaces impose equal physical V and opposing inward I. Thus
internal waves swap between connected conductor endpoints. For block scattering
B, internal permutation P and exterior injection E, solve (identity-PB)X=E,
then the unmodified cascade scattering is S=E.T B X. No growing transfer-matrix
product is used in production.

At each exterior terminal use lumped Zs=R+j omega L and Yc=j omega C, where
R,L,C have units ohm,H,F. Source current Is=Iline+Yc V and source voltage
Vs=V+Zs Is. Substitution into RMS wave definitions gives Ys=1/Zs,
Yt=Ys+Yc, Gamma=(1-Z0 Yt)/(1+Z0 Yt),
d=sqrt(Z0) Ys Vs/(1+Z0 Yt), and a second direct solve:

```
[identity-diag(Gamma)S] aext = d
alocal = X aext
```

Both internal and endpoint systems retain their own condition/residual checks;
a good endpoint condition alone cannot qualify the internal connection. The
unchanged cascade is then actually executed with the solved exterior incident
waves. Its complete child request/digest/network, ordered section drives,
modal/physical fields and individual heat splits are rebound before accepting
the output. Reconstructed physical exterior/junction/heat ledgers must match the
retained child ledgers exactly. This equality checks deterministic provenance;
independent physical equations supply the accuracy oracle. There is no reference
conversion, interpolation, hidden regularization or clipping.

## Work, heat and energy for future multiphysics coupling

RMS complex source work Ss=Vs conj(Is), exterior line power Sl=V conj(Iline),
terminal resistor heat PR=R abs(Is)^2, mean stored UL=L abs(Is)^2/2 and
UC=C abs(V)^2/2 satisfy Ss-Sl=PR+j2 omega(UL-UC). Ideal laws
vL=L di/dt and iC=C dv/dt give these mean energies by direct time averaging.
Source VA, reactive var, average energy J and real heat W remain separate.
Absorbing sources retain negative real source work. Source current and line
current differ by the shunt capacitor current, which is returned explicitly.

Global real source work equals terminal resistor heat plus the sum of actual
section conductor/dielectric heat. Ideal interfaces contribute zero net power;
modal losses and internal transfers are never counted again as heat. Section IDs
own pair-level integrated loss, not an inferred individual conductor share of
mutual terms or a physical thermal cell. Every sampled positive frequency is an
independent steady scenario, without automatic frequency summation or a transient
thermal history. These distinctions preserve a future explicit coupling boundary
without claiming thermal deposition, temperature feedback or contact readiness.

## Exact primary-source review and clean-room rights

Reviewed20 October2026: D.H.Staelin, *Electromagnetics and Applications*, MIT
online text(2011), [official chapter8 PDF](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf).
Actual full-text review: section8.1.2 printedpp232-234 for physical junction
continuity; section8.1.4 printedpp236-237 for reactive load/Thevenin treatment;
section8.3.1 eqs8.3.1-8.3.9 pp249-250 and eq8.3.16 p251 for complex line laws
and dissipation, reviewed for the preceding constituent stages. The original
composition above independently combines those foundations and the already
reviewed constituent methods; it does not infer broadband transient validity from
the source's examples. Peak-phasor loss factors are converted to RMS conventions.
RMS mean-energy and terminal complex-power identities are independently derived
here, not attributed to unreviewed energy sections. No external implementation,
code, prose, figure, mesh, model or dataset was copied, translated or adapted.
References establish physics lineage, not implementation rights or validation.
New SPIKE-owned material is Apache-2.0; NumPy/SciPy dependencies remain unchanged.

## Numerical envelope and failure behavior

Admit1..8 sections,1..1024 samples,1..32 probes/section; R1e-6..1e12 ohm,
L0..1e3 H,C0..1 F. Numerical admission is not physical validation of every
parameter combination. Input<=8MiB and result<=32MiB, with a conservative
combined preflight, streamed retained-child/final size checks and the inherited
100million connection-work bound. Dense internal order<=32; endpoint order4.
Internal and endpoint conditions<=1e8; raw direct-solve residuals<=1e-10 scaled
norm. KVL and V/I continuity tolerance1e-9; per-terminal complex-power/global
heat residual tolerance1e-10 scaled power. Raw constituent conditions and
residuals remain visible in the nested result. Underflow/overflow, nonfinite
arithmetic, singularity, unsupported data, cancellation or callback failure
reject atomically. Poll during admission, bare section/connection work, endpoint
feedback, actual child execution/binding and result assembly. No successful
partial field or residual redistribution is returned.

No new time/space approximation is introduced. Homogeneous section subdivision
is invariant; quadrature32/64 refinements establish reference heat integration.
Frequency rows are not interpolated and do not establish causality/convergence
of a material fit. Exact equality of canonical child records checks identity and
integrity, not accuracy or experiment. Recomputing bare internal data adds
verification cost; no acceleration or performance-parity claim is made.

## Verification and remaining validity

Frozen acceptance uses V/I absolute2e-11 plus relative2e-9, heat/complex power
absolute2e-12 plus relative2e-9, mean energy absolute2e-20 J plus relative2e-9.
An independent direct physical self/mutual four-state spatial chain uses matrix
exponentials and RLC endpoint equations, without production modal transforms or
wave feedback. It reuses only the preceding test oracle's independent physical
coefficient assembly; its zero-drive wave boundary solution is discarded.
Physical RLC KCL/KVL supplies a new endpoint solve. Every section probe V/I and
terminal current/voltage/complex power/energy is compared. Independent physical
quadratic32/64-node integration verifies each conductor/dielectric loss split.
One-section S09 equivalence, zero-L/C physical resistive limit, homogeneous
subdivision, zero/scaling/order/permutation/reversal, absorbing-source signs and
large J versus W test limiting cases. Malformed grids/references/identities,
condition/resource/cancellation/callback and forged child provenance, network,
interior field, total-preserving heat split, aggregate/junction ledger or section
order all reject. Actual worker/CLI/example, strict schemas, review and
source-bound execution support the [validation record](validation/SI02_LOADED_CASCADE_20261020.md).

General terminal topology, ideal open/short, nonlinear/lossy/frequency-dependent
reactives, asymmetric/noncommuting matrices, branching, geometric
bend/via/launch/return parasitics, DC/transient/causal initialization, radiation,
thermal allocation/feedback, measurement correlation and original-board
qualification remain open. Human numerical review is required before release;
full PI/SI and multiphysics parity are not established by this stage.
