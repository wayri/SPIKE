<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent review of one source-informed initial-field diagnostic

Integration-owner derivation before implementation, 2026-10-24. The independent
proposal is `output/promo-propulsion-pod-20261023/real_motor/30dh-next-step-independent-proposal-20261024.md`
(SHA256 `2ec2fbecea1818c25fdcb895bb38d68377d74b2f5396ab1973b39ede07a13cef`).
It addresses the failed exact-30DH stationary experiment, not a change of law,
reference preconditioner, range guard or final residual criterion.

At the fixed angle, the existing expansion a_d=P_d z is linear in the joint
interior/Fourier unknown z, with homogeneous outer gauge. Its trace relations
therefore survive global scaling. For straight P2 elements, curl(P_d z) is
affine in barycentric coordinates, and its norm anywhere is at most the
largest vertex norm. Recover the same-source linear reference zL, and compute
M=max |curl(P_d zL)| over every vertex of every replaced steel element.
The single declared beta=min(1,0.8 Bmax/M), or one for M=0, gives seed beta zL.
Verify actual scaled maxima and full expansion; do not clip individual fields
or scale PM/current sources. This proves feasibility of the initial guess
only, not equilibrium, an admissible Newton path or an in-range root.

The reference is positive definite after the existing gauge, and Kref zL=f.
Both the target and reference have the same load at zero potential, so
r(0) dot zL=-zL dot Kref zL<0 for nonzero f. A sufficiently small positive
scale lowers the target potential, but the chosen fixed beta need not do so
and need not lower residual norm. Measure the target seed residual/potential
using the unchanged owner. Reject the experiment if its residual does not
improve the pinned zero-start value or its potential exceeds the old value
beyond the existing roundoff allowance. This also prevents a different initial
residual from silently loosening the existing relative stopping threshold.

Only one existing Newton/CG/Armijo step is proposed, with max_iterations=1,
the same actual CG residual criterion, all 48 range/energy trial steps, and no
sensitivities. Expected nonconvergence after one step must remain explicitly
unsolved. The diagnostic compares residual, potential, alpha and direction
cost against the old four-step history; it does not accept a stationary torque.
No full 110-second retry, alternative beta search, extra factors or tail is
admitted. Any later converged result must still meet the old absolute final
residual cap as well as its own unchanged owner criterion.

The reviewed P2 polynomial basis and magnetic energy foundations remain those
in `PROPULSION_POD_NONLINEAR_P2_20261023.md`; the owner independently read the
[DefElement degree-two triangle](https://defelement.org/elements/examples/triangle-lagrange-equispaced-2.html)
basis and explicit six nodal functionals on 2026-10-24. The proposal records
the primary Stanford Newton/backtracking and SciPy 1.17 CG sections actually
reviewed by its independent author. No external numerical implementation or
fixture was inspected or copied for this diagnostic.

Before launch require source/curve/reference pins, exact seed packing and
expansion checks, fresh 4 GiB physical / 8 GiB commit headroom and no competing
heavy job. Use matching motor Python 3.12.9, BLAS1, OS 180 s / 2 GiB, prepare
including seed recovery <=120 s and field <=45 s. Bound incremental seed and
diagnostic storage to 8 MiB; at most 4 MiB of explicitly unsolved vector
checkpoints may be written. Instrumentation and asset attribution require
review. None of this establishes H070 identity, convergence, physical loads,
thermal qualification or GUI readiness. Human numerical review remains
required before release.
