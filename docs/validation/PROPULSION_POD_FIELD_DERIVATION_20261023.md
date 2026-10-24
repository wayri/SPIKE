# Reciprocal planar PM field ports — 23 October 2026

## Scope and source lineage

`python/spike_core/propulsion_pod_field.py` adds a bounded synthetic **two-phase, one-pole-pair, linear-recoil planar PM port model**. It reuses the existing `magnetic_fem.solve_magnetostatic` P1 implementation for four actual basis solves. Every subsequent port/field evaluation is exact linear superposition of that same discrete model, not an independently supplied torque/back-EMF constant. No existing solver implementation is changed.

The fixed circular rotor is represented by a conforming inscribed polygon; only its uniform remanence direction rotates. Its scalar recoil permeability is isotropic and fixed. Two stationary axial winding pairs occupy four annular sectors. This is an idealized circular-rotor reference, not a sourced three-phase BLDC, VESC firmware, the mechanical pod motor, moving-conductor eddy simulation or a qualified drive. End turns, winding resistance, leakage outside the 2D extrusion, losses and controller/shaft/propeller integration are not inferred here.

Primary references reviewed on 23 October 2026:

- Haus and Melcher, *Electromagnetic Fields and Energy*, [§11.7, Macroscopic Magnetic Forces](https://web.mit.edu/6.013_book/www/chapter11/11.7.html), especially terminal electrical work, the energy/coenergy transformation and reciprocal mutual inductance. These provide the conservation basis; implementation below is independently authored.
- J. L. Kirtley Jr., MIT 6.685, *Class Notes 1: Electromagnetic Forces*, dated 5 September 2005, [energy conversion and coenergy sections](https://web.mit.edu/course/6/6.685/www/chapter1.pdf). Reviewed for phase-port work and torque as the mechanical-coordinate derivative of coenergy. Its synchronous-machine illustration is not imported as geometry or assumed winding parameters.
- D. Meeker, *Magnetic Circuit Derivation of Energy Stored in a Permanent Magnet*, dated 5 April 2007, [linear recoil PM reference and coenergy discussion](https://www.femm.info/doku/doku.php?id=pmenergy). Reviewed for consistent PM source/reference treatment; no external implementation or data are copied.
- COMSOL 6.4 AC/DC theory, [Electromagnetic Energy, Coenergy, and Virtual Work](https://doc.comsol.com/6.4/doc/com.comsol.help.acdc/acdc_ug_theory.05.79.html), reviewed for distinguishing fixed-current coenergy work from fixed-flux energy work. This does not establish solver correlation.

## Independent discrete derivation

Let a contain free nodal Az in Wb/m, d be extrusion depth in m, Gₑ the P1 curl mapping, Aₑ the triangle area, and νₑ=1/μₑ the fixed scalar reluctivity. The outer boundary is Az=0. A connected mesh and the essential boundary remove the gauge nullspace. Assemble the symmetric positive-definite free stiffness:

`K = Σ Aₑ Gₑᵀ νₑ Gₑ`.

Each phase has signed winding density χₑk in m⁻². Positive and negative regions are normalized **individually by their actual discrete area** to +N and −N turns. Thus `Jzₑ=Σ χₑk iₖ` in A/m². Define the source columns `Cₙk=Σₑ Aₑ χₑk Nₙ/3` using exact P1 element-average shape weights. This source/extraction pairing is essential. Because `Σₙ Cₙk=0`, adding a constant to Az leaves the phase linkage unchanged.

Inside the PM take the admitted reversible law `H=ν(B−Br)`, with `Br(θ)=Br₀(cosθ,sinθ)`; elsewhere Br=0. Rotating the remanence in the ideal circular isotropic rotor leaves K fixed. Its nodal source is `f(θ)=F r`, where `r=(cosθ,sinθ)` and the two columns of F are assembled through the existing kernel's zero-potential PM residual. The discrete field equation is:

`K a = C i + F r`.

For this **linear admitted material model**, solve the existing kernel once for each column of C and F, retaining `Aᵢ=K⁻¹ C` and `Apm=K⁻¹ F`. This is a four-column exact discrete response basis, not a fitted surrogate. It is invalid for a changed mesh/material law, nonlinear saturation, changing permeability or moving geometry. Such changes require rebuilding or a different verified method.

The same winding source extracts physical linkage:

`λ = d Cᵀ a = L i + M r`,

`L=d Cᵀ K⁻¹ C`, `M=d Cᵀ K⁻¹ F`, `S=d Fᵀ K⁻¹ F`.

L has units H and is symmetric positive definite for these independent admitted windings. M has units Wb-turn; S has units J. Its symmetry follows from the same fixed symmetric K, rather than enforcing an arbitrary torque constant or clipping a nonreciprocal matrix.

The existing kernel reports the constitutive reference `ν(|B|²/2−B·Br)`. This port model explicitly adds the angle-independent recoil PM constant

`c=d ΣPM Aₑ νₑ |Br₀|²/2`.

Consequently its defined energy functional is the integral of `ν|B−Br|²/2` in the PM and `ν|B|²/2` elsewhere, under the admitted fixed linear recoil assumptions. Its current-controlled variational functional is

`Π(a,i,θ)=d[.5 aᵀ K a−aᵀ F r−iᵀ Cᵀ a]+c`.

At the stationary field solution define coenergy `W′=−Π*`. Writing `Cpm(θ)=.5 rᵀ S r` yields

`W′=.5 iᵀ L i+iᵀ M r+Cpm−c`,

`U=iᵀλ−W′=.5 iᵀ L i−Cpm+c`.

The **bare** positive quadratic `.5 d aᵀ K a` is not the correct energy for the coupled circuit/shaft ledger: PM source work must be included. U above matches direct kernel constitutive energy plus c, as checked independently in tests. W′ may be negative under this explicitly stated reference; this is not a negative inductance or active winding law.

With `r′=(−sinθ,cosθ)` and `r″=−r`:

`τ=∂W′/∂θ=iᵀ M r′+r′ᵀ S r`,

`∂λ/∂θ=M r′=∂τ/∂i`,

`∂τ/∂θ=−iᵀ M r−rᵀ S r+r′ᵀ S r′`.

These derivatives use the same solved field basis. The PM self term is retained even though the fourfold symmetric reference makes it constant to numerical precision; it is not discarded on an untested symmetry assumption. A caller's physical terminal equation is `v=R i+dλ/dt`, with separately supplied R and any explicitly excluded end-turn terms. The motional back-EMF is `(∂λ/∂θ)ω`. No unrelated Ke or Kt is added. Phase-current alignment for positive torque follows the returned derivative vector; the phase axes must not be assumed to follow an unrelated d/q convention.

## Finite-step interface for the coupled owner

The class exposes constant read-only `inductance_h`, `pm_flux_basis_wb_turn` (M), `pm_self_matrix_j` (S), plus `coupling_terms(θ)` returning ψ=Mr, ψ′, Cpm, Cpm′ and c. `evaluate([ia,ib],angle_rad,include_field=False)` returns flux, torque, U/W′ and angular derivatives. Optional field output includes the actual reconstructed P1 potential/B/H, mesh, remanence, normalized winding densities and the **current-dependent** Jz. Thus closed-loop fields can depend on the accepted terminal state instead of animating an unrelated fixed-current result.

For endpoints with angle difference δ and midpoint θm, exact stable harmonic secants are

`Δψ/δ=ψ′(θm) sinc(δ/2)`, `ΔCpm/δ=Cpm′(θm) sinc(δ)`,

where sinc(x)=sin(x)/x, with its continuous value at zero. The second expression follows from the constant/2θ terms in Cpm, not a first-harmonic approximation. With current midpoint ī, discrete torque

`τDG=īᵀ(Δψ/δ)+ΔCpm/δ`

satisfies the exact discrete magnetic-port identity `īᵀΔλ=ΔU+τDG δ`. This is tested for finite simultaneous current/angle changes. The full controller, winding resistance, mechanics, aerodynamic reaction, time-step admission and rollback remain the coupled owner's responsibility; this module alone does not claim the completed pod loop.

## Validation actually executed

Commands:

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_propulsion_pod_field tests.python.test_magnetic_fem -v
.venv/Scripts/python.exe -m unittest tests.python.test_magnetic_machine_study tests.python.test_machine_geometry -q
```

**41 tests passed, zero skips**: eleven new port tests, twelve retained P1 kernel tests and eighteen retained machine/geometry tests. New tests independently re-solve the full PDE with actual combined Jz/rotated Br, integrate linkage by element quadrature, and obtain torque by centered virtual work of the full kernel constitutive/source functional at two perturbed angles. They also check signed turns and gauge invariance, symmetric positive L/current derivatives, angle derivatives and torque/current reciprocity, continuous power/shaft energy, exact finite-step port energy/harmonic secants, period/current reversal, zero remanence, mutation isolation and strict nonfinite/bool/budget rejection. Shared pure specification validation is checked without invoking a field solve. The virtual-work test is an independently reduced full PDE check; no Maxwell-stress accuracy claim is substituted for it.

Default mesh: 705 nodes, 1344 triangles; four actual basis solves have residual norms at most 3.07e-11 A. At i=(5,−2) A, θ=0.4 rad, actual field-derived torque is −0.00571245748 N·m and L diagonal is 18.0009154 µH. Signed turn integrals sum to within 9e-16. These characterize a numerical reference, not a hardware torque constant.

An executed geometry ladder, otherwise identical, gives:

| Target edge | Nodes / triangles | LAA (µH) | ψB(0) (mWb-turn) | Torque at (5,−2) A, 0.4 rad (N·m) |
| --- | --- | --- | --- | --- |
| 4 mm | 705 / 1344 | 18.0009154 | 1.50033406 | −0.00571245748 |
| 2 mm | 2129 / 4144 | 18.5021376 | 1.49877759 | −0.00572683363 |
| 1 mm | 8289 / 16352 | 18.6500333 | 1.49899647 | −0.00573381153 |

Differences decrease for L and this torque sample, but this is not an exterior-boundary study, general error bound or hardware validation. Rotor polygon/interface, finite Az=0 exterior and 2D extrusion errors remain. No time integrator or loss model is added in this module. No full repository test run, external FEM correlation, measured motor reference or production qualification is claimed. Knowledgeable human numerical review remains required before release.

## Source/version record

Method revision: `FieldMotor`, `spike/propulsion-pod-field-state/v1`, authored 23 October 2026. Existing P1 kernel `python/spike_core/magnetic_fem.py` SHA-256 `ae92fe4e55ea0e5a1fa37369daa219c6e110589bae93ea5e20faa1b85f2c18ff` was reused unchanged. The new method, tests and this derivation are the only owned artifacts. Parent integration/review must bind their final hashes and its independently authored assessment; this authoring record does not claim independent approval of itself. Defaults and all input bounds are explicit in `DEFAULT_SPEC` and the pure `validate_field_spec` function reused by constructor admission. Validation normalizes a fresh dictionary and checks the node budget without meshing or solving; this extraction leaves the numerical method unchanged.
