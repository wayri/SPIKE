<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Three-dimensional CHT numerical evidence, 20 October 2026

Status: experimental numerical verification, not hardware validation or release
qualification. Original implementation, derivation and synthetic data; no
external source implementation, examples, figures or measured data were copied.

## Governing model and discrete derivation

Constant incompressible Newtonian momentum satisfies
`rho (u.grad)u - mu laplacian(u) + grad(p) = b`, `div(u)=0`.
The [separate laminar ledger](ENCLOSURE_LAMINAR_METHOD_20261020.md) derives the
staggered skew transport and kinetic identity. Existing creeping flow omits
inertia explicitly and retains its own regime admission. Geometry and velocity
transfer are derived in [the refinement record](../ENCLOSURE_REFINEMENT.md).

Sensible energy, for constant properties, is
`rho cp dT/dt + div(rho cp u T) - div(k grad(T)) = q` in fluid, and the
same equation with `u=0` in solid. Units: rho [kg/m3], cp [J/kg/K], mu [Pa s],
k [W/m/K], b [N/m3], q [W/m3], p [Pa], u [m/s], T [K]. Thermal contact here is
perfect: no extra contact resistance is inferred. On an orthogonal shared face,
independently integrating the two half-cell Fourier drops gives

```text
G_PN = A / (dP/kP + dN/kN)                         [W/K]
Q_PN = G_PN (TP-TN)                               [W]
F_PN = rho cp (u.normal) A                        [W/K]
H_PN = F_PN * (TP if F_PN>=0 else TN)              [W]
```

Each signed face term enters its two cells with equal and opposite sign. At a
solid interface `F=0` is required exactly. The two reconstructed interface
temperatures are `TP-Q*dP/(kP*A)` and `TN+Q*dN/(kN*A)`; their difference is
measured. A convective exterior boundary adds resistance `1/h` [m2 K/W] to the
half-cell resistance. Prescribed exterior flux enters with its supplied inward
sign. Summing all rows eliminates internal faces without a rank-zero field
reconciliation or a correction to the computed heat.

Backward Euler uses `M=rho cp V` [J/K] and
`(A+M/dt) theta_new = rhs + (M/dt) theta_old`, where theta is temperature
relative to the supplied initial temperature (transient) or minimum thermal
anchor (steady). Solving rises avoids cancellation in exact uniform states.
One factorization is reused because flow, properties, sources and dt are fixed.
At each step `generated - outward - stored_rate` is checked in W; accumulation
of actual endpoint boundary heat checks startup storage in J. This is first
order in time. Upwind thermal transport is first order and introduces false
diffusion; no higher-order thermal claim follows from the momentum stencil.

## Conditioning and accuracy repairs

Independent review found a large-origin counterexample: origin `1e15 m` with
nominal spacing `0.3 m` produced represented widths 0.25/0.375 m. The mesh now
requires actual coarse and refined widths to match declared widths within
`1e-10` relative error. Flow/thermal composition separately checks transferred
divergence against the original momentum metric, not only against itself.

A second counterexample used a 3-cubed grid, 1 mm cells, conductivity 1e5 W/m/K,
convection 1e-12 W/m2/K and opposing 1e12 W/m3 source/sink slabs. Small relative
diffusion residuals concealed an arbitrary constant temperature error. The
thermal solve now probes `x=A^-1 1` using its actual factorization. For the
assembled Z-matrix (nonpositive off-diagonals), a positive x with `Ax>0` makes
`A diag(x)` strictly row diagonally dominant; hence A is a nonsingular M-matrix.
Its inverse is nonnegative. If `r=||Ax-1||inf<1`, exact arithmetic gives

```text
||A^-1||inf = ||A^-1 1||inf <= max(x)/(1-r)
cond_inf(A) <= ||A||inf * max(x)/(1-r).
```

Admission requires finite positive x, probe residual <=1e-6 and indicator
<=1e10. This is a floating-point diagnostic, **not an interval-certified bound**.
No absolute watt floor excuses unbalanced tiny-heat cases; raw balance must
meet `1e-7` times the actual generation/outward/storage scale. Rejected solves
never publish fields, including oversized/nonfinite final publication.

The exact weak-anchor case now rejects; h=1000 W/m2/K control succeeds with
symmetry mean 299.99999999997004 K. Independent dense infinity-norm conditioning
was 9.882361139931575, versus reported 9.88236113993159. A separate transient
constant-heating check had integrated defect 3.47e-18 J. Reproduction script
and source hashes are retained locally in
`build/enclosure3d-review-20261020/{recheck.py,RECEIPT.md}`. This bounded agent
review does not substitute for required knowledgeable human numerical review.

## Reviewed primary sources and exact access scope

- NIST FiPy **4.0.3**, numerical
  [discretization](https://pages.nist.gov/fipy/en/stable/numerical/discret.html)
  (cell-centered finite volume, transient/convection/diffusion sections) and
  [schemes](https://pages.nist.gov/fipy/en/stable/numerical/scheme.html)
  (central/upwind coefficients, positivity and false diffusion), documentation
  updated 18 June 2026, read 20 October 2026. Mathematical text only; no FiPy
  source or examples adapted. Orthogonal-grid limits remain explicit.
- NASA NPARC [spatial convergence](https://www.grc.nasa.gov/WWW/wind/valid/tutorial/spatconv.html),
  grid considerations and order/asymptotic-range sections, read 20 October 2026.
  Supports separate refinement studies; not evidence of physical validation.
- N. J. Higham, [What Is a Condition Number?](https://nhigham.com/2020/03/19/what-is-a-condition-number/),
  author explanation dated 19 March 2020, opening norm/conditioning/sensitivity
  discussion read 20 October 2026. The positive constant-vector probe and
  residual-adjusted M-matrix argument above were independently derived.
- SciPy [splu documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.splu.html):
  current site **1.18.0** API/CSC factorization and factor.solve semantics reviewed
  20 October 2026; actual tested runtime **1.17.1**. Version-specific 1.17.1
  URL was unavailable, so no claim of that page being reviewed. Installed API
  behavior was executed in tests. Existing NumPy/SciPy dependencies only.

## Executed acceptance and reproducibility

The permanent tests cover exact three-material series conduction and interface
temperature; nonzero 3-D creeping recirculation with solid heat; inertial fluid
box composition inside solid walls; conservative manual thermal refinement;
uniform multi-material startup storage; exponential transient refinement;
resource, malformed/unknown-field, cancellation and both accuracy counterexamples.
`scripts/benchmark_enclosure_cht.py` provides source-bound requests/results and
convergence receipts. A smooth three-dimensional sine-temperature continuous
conduction oracle also checks nonzero spatial truncation and observed order.
See the runner output for actual errors and orders; no hand-edited
expected-result file is used as a successful solver run.

Residual, energy and mass gates verify the implemented discrete problem, not
that a supplied grid resolves a real flow. Momentum has a three-component
manufactured solution with independent continuous forcing. Thermal transient
refinement uses an independent exponential. The exact layered case has zero
truncation error for its piecewise-linear solution and therefore is **not** a
general thermal spatial-order benchmark. The separate smooth conduction test
has observed orders 2.03375 and 2.01060, finest relative temperature-rise L2
error 0.0057312. The separate non-tangent advective case below supplies bounded
coupled spatial verification. General geometry/property/flow validation,
independent CFD and measured correlation remain open.

An additional diagnostic tried the same sine temperature with the full curl
velocity. Its errors at 4/8/12 cells per axis were 0.0301087197963,
0.0141448822151 and 0.0112627191138: observed orders 1.08990 and 0.56196.
The latter fails the declared 0.7 order budget; it is **not qualified** by these
grids and the gate was not relaxed. Inspection also showed that this velocity
is analytically tangent to that temperature, so its continuous advective term
is identically zero. A genuinely advective manufactured case must use a
non-tangent temperature; passing conduction/conservation cannot stand in for
that check. This failed diagnostic is retained, not counted among passing cases.

The independently differentiated non-tangent case uses
`theta=sin(pi*x)^2 sin(pi*y) sin(pi*z)`,
`q=2*pi^2*(sin(pi*x)^2-cos(2*pi*x))*sin(pi*y)*sin(pi*z) + u.grad(theta)`.
The continuous advective source is nonzero (sample maxima 2.30 to 2.62 W/m3).
Actual coupled 4/8/12-grid temperature-rise errors are 0.104548460958,
0.031472811096 and 0.018313299647, with orders 1.73199 and 1.33549. Both pass
the unchanged minimum 0.7 order gate and the finest error is below 0.1.
This supports convergence of this first-order upwind composition, not general
second-order advective accuracy. Emitted-face mass, independent generated W,
outward W and momentum residual are checked separately in
`tests/python/test_enclosure_cht_advection.py`.

## Local execution record

Final benchmark: `build/enclosure-cht-benchmark-20261020-final/receipt.json`,
SHA-256 `699f469a98bad491fb16adcf2d212d71b166bed08f2af7050e6a57426ca9ea0d`.
Sixteen exact requests/results are retained with nine unchanged bound source
hashes. Thirteen executed CHT pairs also passed strict request/result schemas;
the other three are separate inertial momentum contracts. The final momentum
finest-error gate is below 0.02 (actual 0.011433), stricter than the early 0.04
harness gate. No failing requirement was relaxed.

The embedded fluid/solid case has a moving 4-cubed fluid region inside a
6-cubed conducting wall layout, a 2.5 W solid source and manual thermal cuts.
Computed Reynolds bound is 5.01749, eight nonlinear iterations, maximum face
speed 2.89685 m/s, prolonged divergence 3.99e-14/s, 168 solid/fluid faces and
maximum interface jump 5.55e-17 K. Maximum temperature is about 300.3351 K and
raw energy balance is 0 W. A separate actual CLI rerun accepted the same source
and balance. This verifies bounded composition, not a real fluid/drive model.

- Python 3.11.9: 125 scoped CFD/CHT tests passed with warnings treated as
  errors, no skips (`build/enclosure3d-final-domain-20261020.log`). Two added
  catalog/headless-worker tests then passed with the publication regression
  (`build/enclosure3d-publication-final-20261020.log`, three tests including
  that repeated regression).
- Python 3.12.9: the earlier 123-test domain matrix passed with no skips
  (`build/enclosure3d-domain-py312-20261020.log`); five final advective/wire/CLI
  additions passed (`build/enclosure3d-final-additions-py312-20261020.log`).
  The two subsequently added catalog/headless checks were run on 3.11 only.
- `ctest --test-dir build/native-cht-20261020 -C Release --output-on-failure`:
  both existing native CTests passed. These exercise existing 2-D executables;
  the new 3-D reference uses the existing Python/SciPy runtime, not a claimed
  new native production backend.
- Actual CFD CLI and generic headless worker exercise completed and rejected
  results. Strict request/result schemas and registered catalog entries pass;
  oversized formatted process results reject without partial fields.
- Architecture guard, scoped diff whitespace checks, reference inventory check
  and Python compilation pass. No UI, package, Linux/MPI or whole-project
  release qualification was performed for this increment.

The first domain attempt used sandbox system temporary directories and hit two
Windows atomic-replace permission errors; seven native tests skipped because
trusted executable overrides were absent. Re-running with workspace-local
TEMP/TMP and actual built native executable overrides produced the zero-skip
results above. No numerical gate or assertion was relaxed. The original log is
retained as `build/enclosure3d-focused-20261020.log`.

No turbulence closure, rotor, moving mesh, compressible energy, fan, buoyancy,
contact law, radiation, mechanical feedback, general CAD or new release package
is qualified. Existing failed PI/release gates remain unchanged.
