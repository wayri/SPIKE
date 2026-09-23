<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Cross-board fields and physical probe modes — 2026-09-07

## Implemented scope

`openems_assembly_geometry` admits explicit per-board material boxes and rigid
axis-permutation placements. It preserves each board's dielectric volumes and
intervening vacuum, rejects overlapping boards, reflections, oblique placements
and unsupported geometry, and emits actual CSXCAD material primitives. This is
not the general DesignIR/curved-PCB conforming compiler. The existing single-board
adapter and assembly-coupled capability gate were not misleadingly relabeled.

`scripts/run_crossboard_openems.py` constructs two facing signal strips with
separate substrates and reference conductors. Four independent field excitations
produce the complete four-port matrix; missing coupling entries are never
inferred from symmetry or a cascade. The example uses explicit box geometry,
Cartesian FDTD and real 50-ohm ports. Board-B voltage polarity follows +z,
opposite its signal-to-return polarity. Finite-conductivity copper cells are
not skin-depth-converged and must not be used to qualify conductor loss.

The runner verifies actual inner eight-cell PML surfaces remain outside all
material volumes, bounds cell count/runtime/artifact size and refuses existing
output directories. It retains source/geometry/worker hashes and logs. A result
marked `executed` is not an accuracy qualification: PML, duration and mesh
convergence must be separately established. Shorter decay settings are explicit
smoke-test choices, not relaxation of a production acceptance gate.

The first completed coarse example (`build/crossboard-field-pml-checked-20260907`)
failed its fixed numerical screen: maximum singular value 1.10410 and reciprocity
error 0.02506. Independent Fourier reconstruction of all 32 terminal histories
found significant incident waves at nominally inactive ports. Dividing each
column only by the driven incident voltage was therefore insufficient.
The reusable `multi_excitation_network.solve_multi_excitation` instead solves
`B = S A` using every measured incident/reflected wave. This is not passivity
projection. On the retained coarse data it yields maximum singular value
1.00217, but reciprocity still fails at 0.02421 versus the unchanged 0.02 screen.
The original result and the separate hash-bound reconstruction are preserved.

The future runner also explicitly pins port midpoints: the coarse voltage probe
had snapped to the strip edge. The stopped mesh-2 baseline and earlier worker
import failures remain recorded; they are not qualifying results.

The corrected 3 mm run, `build/crossboard-field-midpoint-matrix-20260907`,
completed all four excitations with unchanged sources. Maximum singular value
is 1.000897 and reciprocity error 0.012379, passing the fixed 0.02 numerical
screens without symmetry or passivity projection. Probe headers confirm the
requested strip-center coordinate is now used. This is still not exact
passivity qualification or physical accuracy validation.

`scripts/export_crossboard_field.py` rejects failing screens and exports the
screened complex matrix as Touchstone plus explicitly terminated cross-board
NEXT/FEXT. The accepted example's `si-export/` includes those artifacts;
`si-export/ui-export/` contains HTML/CSV with 404 numerically checked retained
sample rows. No DC or transient response was invented for the 0.2–3 GHz band.

All three corrected field runs (3, 2.5 and 2 mm) completed with unchanged
sources and passed the same per-run numerical sanity limits. However,
`build/crossboard-field-three-mesh-20260907.json` **fails** the 0.02 mesh-stability
screen: successive maximum complex-S differences are 0.04686 and 0.04104.
Accordingly this full band remains unqualified. No threshold was relaxed,
matrix projected, coarse case discarded or accepted bandwidth silently reduced.
Further spatial refinement, port-discretization and PML/duration sensitivity
work is required; this is a numerical development item, not an owner approval.

The final focused regression passed 57 Python tests with warnings treated as
errors and the architecture guard. Actual field runs are separate evidence,
not included in that unit-test count.

## Actual physical-mode reference case

`si_ringdown.qualify_ringdown` identifies a single observable decaying mode from
real post-source time probes. Full waveform reconstruction, observation-window
and decimation checks reject inadequate or multimode records. Q uses amplitude
decay `exp(-alpha*t)`, hence `Q = pi*f/alpha`; it is total observed decay, not
separately identified conductor, dielectric, radiation or external-loading Q.
No harmonic-inversion implementation was copied from another project.

`scripts/run_openems_cavity_ringdown.py` executes three actual FDTD meshes of a
homogeneous conductive PEC cavity, with a spatial modal impulse and independent
analytical Maxwell reference. The accepted evidence is
`build/openems-cavity-ringdown-reference-20260907/report.json`:

- Finest frequency error: 0.02336%; Q error: 0.02577%.
- Three-level frequency/Q errors decrease; window/decimation checks pass.
- All explicit analytical errors are below 0.1%; source hashes stayed unchanged.
- Decay-rate error is small but nonmonotonic; no asymptotic decay order is claimed.

This qualifies that reference case only. It does not establish arbitrary
eigenmode completeness, hidden-mode exclusion, open-system modal normalization,
or general physical PCB resonance qualification. Raw probes and logs are retained.

## Remaining acceptance boundaries

General cross-board DesignIR extraction still needs curved/cutout/via geometry,
arbitrary placements, verified interface and port construction, independent
field comparisons and appropriate frequency-dependent materials. A trusted
explicit geometry example is not a replacement for that compiler.

Measured correlation requires matching geometry, feed, materials, boundary
conditions, calibration and uncertainty. The NBS Yagi comparison being exercised
is an exploratory simplified model; its feed and environmental differences
must remain explicit. Failed pulse/decay runs are not physical discrepancies.
Importing Cambridge measured Touchstone data alone remains postprocessing,
not geometric solver validation.

The completed NBS Yagi run reached full excitation and -50.70 dB decay. Its
accepted-power forward gain was 9.418837 dBi versus the published 9.26 dBi,
a +0.158837 dB difference. Radiated/accepted power was 1.004213. This passes
the stated temporal/power screening, not geometry-matched or mesh-converged
measurement qualification. See [the detailed comparison](NBS_YAGI_COMPARISON.md)
and `build/nbs-yagi-fullpulse-20260907/power-normalization-correction.json`:
the latter corrects absolute-power labels without overwriting original evidence.

HTML visual inspection remains blocked by the browser URL policy. No alternate
browser, localhost proxy, screenshot or indirect route was used to bypass it.
Numerical/export tests cannot replace an actual visual acceptance review.

## Reproduce

Use new output paths; commands do not overwrite prior evidence:

```powershell
python scripts/run_openems_cavity_ringdown.py --output build/cavity-reference-new
python scripts/run_crossboard_openems.py --output build/crossboard-new --mesh-mm 3 --end-criteria 0.0001 --timeout 600
python scripts/export_crossboard_field.py --case build/crossboard-new --output build/crossboard-new/si-export
```

An installed openEMS Python runtime is required. In the restricted Windows
tool sandbox, termination of a solver child may require approved escalation;
the failed attempts are retained and not advertised as containment qualification.
