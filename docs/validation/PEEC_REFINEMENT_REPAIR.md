# PEEC refinement repair work

Status: in progress; not release qualification. Existing unrelated working-tree
changes are preserved. Installed binaries have not been updated by this work.
The later [2026-09-28 foundation increment](PEEC_FOUNDATION_INCREMENT_20260928.md)
adds bounded local copper refinement, exact rectangle-spoke RT0 condensation,
and a separated-annulus native kernel. Its pinned Marble rerun still fails
the two-step 2% DC resistance convergence gate at a half-size interior rule.
A subsequent, finer quarter-size interior 0.5/0.25/0.125 mm series passes that
specific DC gate. None of these changes admits Marble AC as qualified.

## Reproduction

`scripts/audit_peec_refinement.py` checks the pinned Marble C383-named rail at
three strictly decreasing mesh sizes. It uses original pad anchors for
U37.18/R195.1 and verifies C383.1 remains disconnected. It checks zone basis
support, DC network residual and KCL, and consecutive R/C changes. It exits
nonzero for a failed gate. It performs no native magnetic quadrature and
therefore cannot qualify L, frequency response, or broadband accuracy.

The initial 1/0.5/0.25 mm reproduction returned R of 4.7788653, 5.2511772,
4.3247098 mOhm with current imbalance below 3e-16 A for a 1 A excitation.
The last relative refinement change was 21.4% (relative to the finer result),
which fails the proposed 2% gate. Small algebraic residuals are not evidence
of correct physical discretization. Evidence is in `build/peec-refinement-fix/`.

## Work boundaries

- Conforming copper partition: independent experimental helper under test;
  finite shared-face currents must stay inside authoritative copper. Area
  omission must be bounded separately from physical accuracy. No silent width
  shrinking, ideal finite-length contacts, or eigenvalue repair is acceptable.
- Capacitance: independently allocated unique physical copper area, separated
  from internal current edges; parallel-plate surrogate remains approximate.
- Transient: shared capacitance estimator replaces duplicate microstrip-edge
  calculation. Explicit returns with no represented return node receive no
  fabricated implicit shunt. A capacitor whose two nodes coincide stamps zero.

The volume-extraction opt-in now selects the unique-source-area C surrogate in
AC and transient through a shared dispatch boundary. The legacy mode keeps its
existing estimator. This does **not** make either mode electrostatically
qualified, and the conforming mesh is not production-wired while its Marble
resource/admission gate fails.

## Current evidence and limits

The area helper's manufactured 2 mm square with h=1/0.5/0.25 mm produced
4/24/112 current branches and 0.708335025024 pF at every refinement (roundoff
variation only). This removes the internal-edge fringing artifact on that
fixture; it does not establish absolute electrostatic accuracy.

The standalone source-area estimator on Marble returned 4.206835435,
4.729905392, and 4.729905392 pF. The coarse mesh has no physical branch for
two pads; all levels explicitly omit via/barrel capacitance. Consequently,
three-level complete coverage/convergence is not achieved. See
[unique copper capacitance evidence](UNIQUE_COPPER_CAPACITANCE.md).
The audit requires complete source coverage before accepting area-surrogate C,
so an apparently flat pair of fine-mesh values cannot hide these omissions.

Exact interior-rectangle coalescing made the geometry-only Marble meshes
admissible under an explicit **sparse DC** resource policy: 32,325/34,078/38,253
branches at 1/0.5/0.25 mm, with zero out-of-copper support and under 1% omitted
area on every layer. The sparse face-resistor audit gives 3.704386/3.815186/
3.797283 mOhm, with successive relative changes 2.904% and 0.471%. The first
change misses the 2% two-step gate; residual/KCL errors are under 2e-12. These
are **not** volume-overlap or magnetic results. The area surrogate is flat at
3.820118 pF but explicitly lacks complete source/via coverage, so the C gate
does not pass. See `build/peec-refinement-fix/conforming-sparse-dc.json`.
At 1 mm the revised surrogate reports zero geometry lookup failures, yet five
unrepresented pad sources and 28,248 omitted via/landing-current branches;
flat C across mesh levels is therefore not evidence of complete capacitance.
An additional 0.125 mm check returned 3.694111 mOhm, a 2.79% change from
0.25 mm; the trend worsens. This is consistent with the documented
non-orthogonal cell-centre face-flux patch-test failure, and confirms that
more geometric cells alone cannot qualify the two-point DC discretization.

An isolated conservative RT0 mixed-DC probe passes affine hanging-face patch
tests, local/global KCL, analytical strip contact refinement, and finite
via-resistance sensitivity. Its hybridized static-condensation form reduces
the global system without changing the finite-contact equations. On the pinned
depth-7/1%-omission Marble geometry, supervised 1/0.5/0.25 mm solves returned
4.884086/4.454536/4.280611 mOhm. Successive changes are 9.64% and 4.06%
relative to the finer result: the two-step 2% refinement gate still fails.
The three active global systems had 144,678/151,462/165,508 unknowns; the
last two required an explicitly raised 200,000-unknown diagnostic cap. Their
relative residuals were below 3.5e-11, cell KCL below 2.3e-11 A, and face
KCL below 5.4e-11 A. These algebraic checks do not establish physical
accuracy. A contact-only 2x2 subdivision on otherwise fixed copper changed
the 0.5/0.25 mm resistances by less than 0.1%, suggesting contact resolution
is not the dominant refinement error. The RT0 path remains a standalone
supervised experiment, not a production DC replacement. The reproducible
command is `build/qualification-py311/Scripts/python.exe
scripts/audit_peec_rt0_refinement.py --board
build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb
--max-unknowns 200000 --output
build/peec-refinement-fix/marble-rt0-dc-audit.json` (run from the repository
root). It exits nonzero because the gate fails.
On fixed admitted copper, splitting only the 400 largest noncontact rectangles
2x2 (a diagnostic, not a proposed mesh policy) changed 0.5/0.25 mm R to
4.269285/4.213759 mOhm. Their difference fell to 1.32%, whereas refining
all 55 contact rectangles 2x2 left a 4.02% difference. This isolates material
interior discretization sensitivity without proving three-level convergence;
the geometry omission and 3D contact/barrel approximations remain separate.
A deterministic optional interior maximum-edge limit is now available without
changing the default mesh. At a limit of half the requested mesh size,
the pinned 1/0.5/0.25 mm audit returned 4.472842/4.296649/4.193589 mOhm.
Changes of 4.10% and 2.46% still fail the two-step 2% DC gate. The exact
command adds `--interior-edge-factor 0.5` to the RT0 audit above and writes
`build/peec-refinement-fix/marble-rt0-dc-interior-half-audit.json`.
At a quarter-size interior limit, an explicitly supervised 210,000-unknown
budget admitted all three levels and returned 4.300546/4.193714/4.139104
mOhm. Consecutive changes were 2.55% and 1.32%, so the first of the last
two changes still exceeds 2%. The report is
`build/peec-refinement-fix/marble-rt0-dc-interior-quarter-audit.json`.
Before rectangle-spoke condensation, a proposed finer 0.5/0.25/0.125 mm
quarter-size series was not runnable within the experimental solver's
250,000-global-unknown cap: the then-current 0.125 mm preflight produced
197,870 triangles and 316,235 globals, although its geometry passed the 1%
area gate. With the exact Schur reduction and current retained partition, the
pinned finer series now completes at 4.193714/4.139104/4.108511 mOhm. The
successive 1.3194% and 0.7446% changes pass the specific two-step DC
resistance gate, with full details and hashes in
[the foundation increment](PEEC_FOUNDATION_INCREMENT_20260928.md). This does
not establish AC R/L/C convergence, scalable field extraction, complete via
coverage, or independent physical validation.

This geometry generates 522–732 million symmetric dense field pairs versus
the native 8,192-pair admission limit, an estimated 93–131 GiB dense workspace.
Consequently the experimental conforming partition is not wired as a production
replacement. It needs a compressed/matrix-free field formulation or a different
geometry-consistent basis; relaxing the pair limit alone would be unsafe.
There is also an independent pair-kernel gap: the current native volume matrix
rejects two spatially separate annular via barrels as
`VOLUME_MATRIX_NONCOAXIAL_ANNULI` and rejects nonperpendicular rectangle/annulus
pairs. Raising the pair budget cannot make an arbitrary multi-via board run.
The pair integrators report quadrature *estimates*, not certified error bounds;
streaming the existing pairs only addresses storage and leaves hundreds of
millions of pair integrations. A researched candidate is a positive-weight
Fourier/Gram representation of magnetic energy with analytic rectangular and
annular basis transforms. Parseval gives a conservative high-wavenumber tail
bound, but finite-domain quadrature and accelerated feature evaluation still
need explicit error control. An isolated C++ prescribed-current prototype and
CTest now cover small cube and mixed rectangle/annulus cases; cube energy was
9.40623e-11 J versus an independent 9.41156e-11 J reference. The finite-domain
quadrature is still **uncertified** and direct feature work is O(bases × nodes),
so this is not a Marble-scale or qualified field solver. Mathematical references:
[NIST DLMF Bessel integrals](https://dlmf.nist.gov/10.22) and
[NIST DLMF Fourier/Parseval identities](https://dlmf.nist.gov/1.14).

The isolated affine-triangle kernel now provides finite conservative envelopes
for singular mutual/self terms, but its self-term envelope remains too broad
even after 200,001 evaluations. It is not production-integrated or qualified.

The KiCad importer now retains explicit roundrect/chamfer ratios and chamfer
corner flags, rather than dropping the data required for faithful pad outlines.
Missing ratios are not invented; invalid values preserve the pad with a
diagnostic. Format reference: [KiCad pad specification](https://dev-docs.kicad.org/en/file-formats/sexpr-intro/index.html).

## Acceptance still required

1. Manufactured support/contact/conservation tests and stable finite pad contacts.
2. Marble admitted geometry without copper leakage, preserving connectivity.
3. Three refinements with the last two R/L changes <=2%, nonworsening trend,
   residual <=1e-7 and KCL imbalance <=1e-8 of excitation. The isolated RT0
   DC resistance portion passed on the pinned finer run; AC R/L has not.
4. Fixed-mesh integration sensitivity <0.2%; C tessellation sensitivity <=2%.
5. Full regression and source/binary identity checks. Independent reference and
   knowledgeable numerical review remain necessary before release qualification.

## Research scope

The abstract of [Ruehli et al., nonorthogonal PEEC formulation (2003)](https://research.ibm.com/publications/nonorthogonal-peec-formulation-for-time-and-frequency-domain-em-and-circuit-modeling)
was reviewed as method context for geometry-consistent PEEC; no implementation
was copied. [Torchio et al., spline-based electrostatic PEEC (2022)](https://arxiv.org/abs/2207.13697)
was reviewed at abstract level as context for separating electrostatic
discretization from geometry representation. Its spline method is not
implemented here. New fixtures, code and acceptance calculations are authored
independently; these citations do not qualify the present approximations.
