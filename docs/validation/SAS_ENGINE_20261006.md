<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# SAS engine capability evidence

This October 6, 2026 development record concerns solver capability and read-only
source admission, not hardware qualification. SAS CAD, vendor models, release
tags, Windows packaging and concurrently owned UI files were not modified.

## Executed checks

The initial native transient/workspace/assembly electrothermal regression run
passed 39 tests. New sourced qualification tests cover real native divider,
RC threshold/refinement, native smooth switch, missing event, unsupported model,
hash/unknown-field/include rejection, admitted include snapshots after disk
changes, actual native event-step caps and immutable CSV/SVG artifact export.
An early example failed because its long first title was parsed as an element;
the original fixture header was changed to an explicit SPICE comment and that
failure bundle was retained. The revised divider/RC example passes both cases.
Its corrected final source/evidence bundle is
`build/sas-engine-qualification-20261006-v3/`. The separate exported synthetic
thermal reference is `build/sas-thermal-reference-20261006/`; its 200 s steady
oracle error is below 2.1e-9 K. Full waveform CSV and SVG plots are retained.

Fourteen transient resistive electrothermal tests cover constant-power RC,
current/voltage-driven R(T), eight synthetic branches, timestep refinement,
loss/mapping completeness, floating networks, temperature/overflow limits,
nonconvergence, cancellation and malformed kernel output. RC temperature errors
at 0.2/0.1/0.05 s steps are 0.035328/0.018020/0.009102 K; current-fed R(T)
errors are 0.035322/0.018011/0.009096 K. The synthetic eight-branch steady oracle
gives device/sink temperatures 321.951219510/314.634146340 K, with tested
nodal/global balance errors below 2.95e-11/2.36e-10 W. These are numerical
references, not a SAS cooling fixture.

Independent review found and repaired two source-checker defects: the nominal
timestep estimate did not limit event-generated native samples, and includes
were reread after hash admission. Actual ABI step limits and immutable include
snapshots now have regression tests. Existing parser/runner defaults are unchanged.

The final integrated focused run passed 111 tests in 13.777 s with warnings
treated as errors. Architecture and changed-document checks passed. Full Python
discovery ran 2,610 tests in 509.622 s: zero failures, two errors and 13 skips.
Both errors were release-verifier tests requiring the absent
`artifacts/releases/beta-0.3.0-beta.1-coherent/SPIKES-0.3.0-beta.1-release.json`.
This does not establish a green release suite; no release payload was fabricated
or acceptance check relaxed. Final additions were covered by the focused run.

## Read only SAS inventory

The final native inventory in
`build/sas-engine-qualification-20261006-v3/sas-native-input-audit.json` records
81 PCB/schematic files matching source_binding.json, with the final source
manifest matching its recorded digest. Original TI archive hashes
match acquisition.json and both extracted model payloads match archive members:

- LM27762_TRANS.LIB: `16c322a7ad5f3ff2b5a7bb1355f4474ec12fe7335487aed5ec1b1dff293af42a`.
- TPS3808G01_TRANS.lib: `f9d87b389c93bfc4c87c7b7d79c31df2a51045bc69b382fdb123c1dad456b651`.

All 15 supplied decks remain BLOCKED at native parser admission. Examples include
standard model-card switch syntax versus the supported native numeric smooth
switch form, extended `.tran`/startup/options syntax and includes outside the
top-level deck's confined directory. Full vendor/controller, four-PNP analog
loading, capture/re-arm/supply-order and floor/CC-CV/short-edge runs have not been
qualified by this native workflow. Hash matches do not prove model authenticity,
physical pin mapping, corner guarantees or redistribution rights.

Existing SAS-side external-run records separately report an original TPS3808
failure, an LM27762 timeout and completion of a syntax-adapted TPS3808 deck.
Those records are observations from that task, not executions by this worker
or validation of the adaptation. Their waveforms require separate admission,
observable extraction and timestep/model correlation before acceptance.

## Remaining requirements

The owner now permits thin low-profile heatsinks on four blades in forced air,
superseding the earlier bare-PCB-only constraint. Local air limits are 40 C
normal and 50 C absolute, including downstream warming. Installed fan operating
point, enclosure inlet/layout, copper/via/contact
spreading, local convection, downstream air rise and Base heat remain unresolved.
No installed heatsink or convection resistance was invented.

The new APIs do not yet provide full vendor-model compatibility, automatic PCB
force/return/harness extraction with thermal ownership, semiconductor switching
loss feedback, dynamic mesh coupling, or exhaustive fault/phase sweeps. Guaranteed
raw pulse capture, hot DC-SOA and measured geometry/cooling correlation cannot
be manufactured by these ideal/reference results. See
[workflow and interfaces](../SOURCED_POWER_QUALIFICATION.md).

## Native filled copper admission repair

The saved Blade import rejects entries 47 through 99 because one B.Cu source
group contains an 87,951-vertex path, beyond the old 65,536-vertex per-component
resource limit. The group has 53 fragments and 112,068 vertices. It is filled
copper, not a rule area; the importer already excludes keepouts. The bounded
path capacity is now 131,072 while the 1,048,576 per-group total and all missing
or malformed fill rejections remain unchanged. Diagnostics expose actual counts
and limits. Source coordinates, identities and fill digests are preserved.

Authoritative flat paths now bypass quadratic simple-polygon repair before
even-odd rasterization. Retraced cutout edges use a direction-independent
intersection calculation, preventing floating-point disagreement on samples
lying on bridges. Original analytical cutout and dense-path admission/rejection
fixtures cover these changes; no external implementation was adapted.

Fresh import admits all 132 filled fragments plus 24 footprint copper graphics.
The native-zones-included steady replay retains eight 3.602526 W losses,
prescribed square contacts, 40 C air, h50 and assumed plating. At 5/2.5/2 mm,
peak board temperatures are 102.391/122.963/123.533 C and maximum junction
estimates are 97.402/101.512/103.679 C. Heat balance errors are below 1e-11 W.
The last peak change is 0.570 K and largest per-component junction change is
4.786 K: comparison gates fail and mesh convergence remains undemonstrated.

The zone-excluded 168.041 to 307.810 C peak shift arose in a model depositing
square-contact power into cells with mesh-dependent scalar copper occupancy.
For Q129, the fraction deposited into cells with zero top-copper coverage grew
from 5.41 to 28.16 percent. Restoring omitted zones is necessary but does not
resolve conforming copper interfaces, actual drain-pad injection, localized
refinement or physical cooling. Nonuniform full-board conservative refinement
and fixed-physical copper sampling remain implementation work.

The installed v0.3.8 desktop, native CAD, source SAS artifacts and QuickTherm
were not changed. Results are developer-source replay evidence, not deployed
installed-assembly qualification.

The final replay bundle is `build/sas-native-copper-replay-20261006-v3/`:
raw requests/results, six component/field CSV files, source/engine digests and
13 artifact hashes verified against `COMMITTED.json`. Its comparison gate is
false and mesh-convergence status is explicitly undemonstrated. Forty-eight
focused importer/raster/layered/contact tests pass with warnings treated as
errors; architecture, changed-document and whitespace checks pass.

The subsequent full Python run executes 2,624 tests in 562.291 s with one
failure, four errors and 13 skips. Two errors require the still-missing coherent
release manifest; two model-library SQLite errors pass in a separate run using
a fresh temporary index. The owned Windows descendant-cancellation test fails
both in discovery and alone, so worker process-tree safety is not qualified.
No affected importer or thermal test failed. These wider issues were not
silently waived or changed by the copper repair.

## Assembly cooling requirements received after the QuickTherm screen

These are supplied requirements, not a new executed study or reviewed fan data:

- Retain four Blade occurrences at the existing 36 mm pitch and corrected
  connector-seated poses. Preserve the original diagnostic project separately.
  Do not change native CAD or use proximity to invent a conductive contact.
- Declared Blade flow is native +X to -X, with two Wakefield
  DC0922512V2B-BT0 fans per case. Installed fan P-Q curves, arrangement,
  pressure losses, blockage and operating point must be reviewed explicitly;
  a fan part number alone is not an airflow boundary condition.
- Include filled copper, narrow trace/plane conduction, plating/via contacts,
  package bulk and junction-to-case/pad paths, electrically isolated TIM/heatsink
  interfaces, and documented Base/connector/mount thermal paths. Missing paths
  must remain unknown, not zero or inferred from nominal spacing.
- Assign per-part operating losses and thermal materials with reviewed,
  assumed or missing status. Separate normal operation, continuous 0.5 A short
  and protection events; do not repeat a single-Blade heat map as an assembly
  solution. Include Base losses and downstream air warming.
- Require feature-aware local resolution of pads, vias, copper necks and
  package interfaces. Compare fixed physical source/site samples, per-device
  junction estimates and field peaks across meshes; energy balance or a small
  linear residual alone does not establish mesh convergence. Display smoothing
  must not imply resolved small features or additional solved samples.
- Normal local air must remain at or below 40 C and absolute local air at or
  below 50 C, including downstream warming. Include fan-loss cases and make
  unmet constraints explicit.

Uniform prescribed h50 and reduced serial air networks remain screening models,
not resolved velocity/pressure CFD. A converged linear solve can still be an
incomplete model. The QuickTherm single-Blade temperatures remain diagnostics:
no new package, flow-field, mesh-convergence or hardware qualification is claimed
by recording these requirements.
