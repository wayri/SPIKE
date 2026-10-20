<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S13: physical RLC endpoints for supplied coupled stars

Experimental development method, 21 October 2026. Compose the unchanged
[ideal coupled star](RLGC_COUPLED_STAR.md) with complete physical source/load
assignments on its 4–16 exterior ports. Each of 2–8 uniform supplied symmetric
legs retains its actual field result and pair-level conductor/dielectric heat.
A positive finite series R, ideal series L and ideal line-node shunt C must be
explicitly assigned to every port, including inactive loads with zero source
voltage. The two ideal conductor junctions remain distinct and lossless.

## Independently derived closure, units and work

Use exp(j omega t) RMS waves V=sqrt(Z0)(a+b), Iline=(a-b)/sqrt(Z0).
The internal star solve (I-CB)X=E, S=E.T B X retains its own condition gate.
At every exterior port let Zs=R+j omega L, Ys=1/Zs and Yc=j omega C.
Physical KCL/KVL give Is=Iline+Yc V and Vs=V+Zs Is. Eliminating V/I gives

```
Gamma = (1-Z0*(Ys+Yc))/(1+Z0*(Ys+Yc))
d = sqrt(Z0)*Ys*Vs/(1+Z0*(Ys+Yc))
[I-diag(Gamma)S] aext = d
alocal = X aext
```

The new direct endpoint solve uses 2m ports; the previous four-port helper is
unchanged. The actual star producer runs with solved exterior waves. Full source
request/digest/network, branch order, local drives, strongly bound modal/physical
fields and canonical node/boundary/heat ledgers are checked before acceptance.
No inverse, clipping, interpolation, reference conversion or regularization.

R, L, C are ohm, H, F; distributed child laws retain ohm/m, H/m, S/m and F/m.
RMS source work Ss=Vs conj(Is), line power Sl=V conj(Iline), resistor heat
PR=R abs(Is)^2, mean UL=L abs(Is)^2/2 and UC=C abs(V)^2/2 obey
Ss-Sl=PR+j2 omega(UL-UC). This follows directly from ideal L/C differential
laws and time averaging. Signed source VA, reactive var, mean J and heat W
remain distinct. Absorbing sources keep negative real work. Global source real
work equals terminal heat plus each leg's conductor/dielectric heat counted once;
ideal node transfers and nested modal heat are never added again.

Named terminals/legs preserve a future explicit multiphysics handoff. No contact
area, mutual-term conductor share, thermal cell or temperature law is inferred.
Each positive frequency is a separate RMS steady scenario, without automatic
sample summation or transient heat history. General topology/asymmetry, piecewise
legs, geometric junction/return parasitics, ideal open/short, nonlinear/lossy or
frequency-dependent endpoints, DC/transient/causal behavior, radiation, thermal
mapping/feedback, measurements and original-board qualification remain open.

## Boundary cancellation repair

The physical oracle exposed a valid almost-zero branch current that the existing
S08 boundary integrity comparison rejected. Two evaluation paths can subtract
nearly equal wave operands; relative error against their small difference is
ill-conditioned. Preserve the existing 1e-9 relative check and add only
64*float64.eps*evaluation_scale at physical endpoint comparisons, where

```
scale_V = sqrt(Z0)*(norm(a_end)+norm(b_end))
scale_I = (norm(a_end)+norm(b_end))/sqrt(Z0)
```

The allowance is about 1.42e-14 of the local wave scale, not a changed engineering
relative tolerance. It is zero for zero operands. Modal-network and interior
probe comparisons keep their previous zero absolute floor; raw fields, all power,
KVL, conditioning and rejection gates are unchanged. A zero true quantity plus
small operand perturbations has absolute uncertainty proportional to operand
size; its relative accuracy cannot be guaranteed by cancellation alone.

Factor 64 is a bounded implementation allowance verified by independent cases,
not a proven error bound for the complete two reconstruction paths: upstream
matrix products may involve remote operands exceeding the local scale. Some
conservative rejection cases may remain. Do not expand the allowance to accept
unresolved cases or claim resolved near-zero relative accuracy. It does not
alter physical currents, zero-fill fields, redistribute residuals or loosen board
convergence/sign-off gates. A native-float corruption at 1e-10 of the local
current operand scale is rejected at the nearly-zero node; eps-scale cases at
three amplitude scales pass, while strict default comparisons still reject.

## Exact sources, review and rights

Physical foundations: D. H. Staelin, *Electromagnetics and Applications*, MIT
online text (2011), [chapter 8 official PDF](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf).
Actual text review on 20–21 October 2026 covers section 8.1.2 pp.232–234,
section 8.1.4 pp.236–237 (reactive/Thevenin treatment), and constituent-stage
section 8.3.1 eqs.8.3.1–8.3.9 pp.249–250 plus eq.8.3.16 p.251. The multiport
composition, RMS mean-energy identities and implementation are independently
and originally derived; the source does not qualify arbitrary star geometry.

Numerical foundation: Nicholas J. Higham, *The Accuracy of Floating Point
Summation*, SIAM Journal on Scientific Computing 14(4), 783–799 (1993),
[author-hosted paper](https://nhigham.com/wp-content/uploads/2023/10/high93s.pdf),
DOI 10.1137/0914050. Full-text review on 21 October 2026 covers model (1.2)
p.784 and bound (2.6) with conditioning discussion p.785. It supports operand-
scaled cancellation reasoning, not the specific factor 64 or a full SPIKE error
certificate. The unavailable blog URL was not used as reviewed evidence.
No external implementation, prose, figures, models, meshes or data were copied,
translated or adapted. New SPIKE-owned material is Apache-2.0; dependencies and
implementation languages are unchanged. Human numerical release review is open.

## Numerical envelope and independent verification

Admit 2–8 legs, 1–1024 exact common positive samples, 1–32 probes per leg;
R 1e-6..1e12 ohm, L 0..1e3 H, C 0..1 F. Admission bounds are not a physical
validity guarantee for their entire Cartesian product. Input <=8 MiB, output
<=32 MiB with conservative preflight and actual streamed size checks. Internal
order <=32, endpoint order <=16; both conditions <=1e8 and raw direct-solve
residuals <=1e-10 scaled norm. Work retains the inherited 100-million-unit bound.
KVL uses 1e-9; complex-power/global heat checks use 1e-10 scaled power. Unsupported,
nonfinite/unrepresentable arithmetic, underflow/overflow, singularity, resources,
cancellation and callback failure reject atomically without successful partial
results. Poll during admission, bare/internal/endpoint work, actual execution,
child binding and result assembly. No new space/time approximation is introduced.

Frozen tolerances: V/I 2e-11 absolute plus 2e-9 relative; heat/complex power
2e-12 absolute plus 2e-9 relative; mean energy 2e-20 J absolute plus 2e-9 relative.
An independent physical 4m spatial boundary/KCL system uses matrix exponentials
and direct RLC exterior equations, without production wave feedback or modal
transforms. Only the preceding independent oracle's physical coefficient assembly
is reused; its zero-drive boundary solution is discarded. Every terminal/probe
field, source current, complex power and energy is checked. Physical 32/64-node
quadratic quadrature verifies each branch's conductor/dielectric heat split.
Two legs agree with S11; matched resistive physical sources reduce to prescribed
star waves. Zero/scaling, record/leg/conductor permutations, absorbing sources,
large storage vs heat and actual eight-leg operation pass. Strict schemas enforce
branch-dependent source/terminal dimensions at two/eight-leg boundaries. Nested
identity/network/probe/heat/node/order tampering, condition/resources and
cancellation/representability failures reject. The standing-wave counterexample
and targeted above-floor forgery remain executable, not hidden by changing data.
See [executed evidence](validation/SI02_LOADED_STAR_20261021.md).
