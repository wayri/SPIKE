<!-- SPDX-License-Identifier: Apache-2.0 -->

# Blender rendering integration plan

**Status: planned; no Blender adapter, installation, render or animation is
claimed by this change.** The interactive field viewer and JSON exchange are
implemented separately. Blender would be an optional presentation package, not
a required solver or a source of engineering results.

## Proposed user flow

Results → Export render scene → choose Static frame or Saved history → review
geometry, field, units, range and output estimate → write a local render bundle
→ open in Blender → preview → explicitly render stills or animation.

Keep this in a contextual tool/editor, with its own hide/restore controls and a
searchable opening action. Do not add a persistent global ribbon. Registration
of an executable and execution/rendering are separate operations.

## Stages and acceptance gates

| Stage | Proposed delivery | Required acceptance |
| --- | --- | --- |
| 1: static scene | GLB geometry plus JSON field/identity manifest; original occurrence transforms, camera, materials, cell/arrow instances and scalar legend | Compare source/Blender bounds and transformed landmarks; verify m/mm conversion, occurrence IDs, color range and exact sample values; render a public fixture |
| 2: saved animation | Explicit frame-time table and field sequence; fixed global legend, camera and geometry; configurable output cadence with saved-sample holds | Uneven timestamps reproduce SPIKE's sample selection; first/final frames and speed agree; no interpolated field is labeled solved; cancel leaves source data untouched |
| 3: large volumes | Optional sparse OpenVDB sequence adapter when topology and sampling support it; label any resampling and retain raw fields | Round-trip coordinate/value checks, bounded memory, CPU fallback, absent-dependency diagnostics and representative supported-GPU renders |

GLB should carry scene geometry and appearance, while the sidecar carries solver
identity, units, quantities, sample times, display mapping, warnings and artifact
hashes. Ordinary geometry animation is not sufficient to preserve arbitrary
time-varying engineering scalar fields. The Blender-side adapter should own
field material/instance updates explicitly.

Photoreal geometry materials and scientific overlays need separate rendering
passes. Use controlled/unlit scientific color mapping with an independent legend
so exposure, lighting, denoising and reflections cannot silently change the
numerical interpretation. Transparent enclosures are visual preferences; they
do not remove fluid/solid geometry from the analysis.

## Runtime and resource policy

Use a separately installed, pinned and tested Blender version, invoked locally
through the existing bounded external-process boundary. Probe supported Cycles
devices rather than promising every GPU/driver combination. Offer CPU rendering
and explicit render quality, frame-count, resolution, memory and duration limits.
Support cancellation, partial output recovery, deterministic camera/seed settings
and a render manifest. Avoid shell-built commands and arbitrary imported scripts;
the reviewed adapter consumes data-only bundles. No cloud upload is required.

No GPU acceleration of the numerical solver is implied by GPU rendering. Keep
engineering material properties distinct from cosmetic render materials. Export
only models/assets with retained rights and provenance; unknown/missing models
must remain identified rather than replaced as authoritative geometry.

## Primary implementation references

These references inform the proposal; version support must be checked again when
the adapter is implemented:

- [Official Blender glTF importer/exporter](https://github.com/KhronosGroup/glTF-Blender-IO): scene exchange and supported extensions.
- [Blender glTF manual](https://docs.blender.org/manual/en/3.6/addons/import_export/scene_gltf2.html): geometry, material and animation interchange boundaries.
- [Blender Cycles GPU rendering](https://docs.blender.org/manual/en/4.2/render/cycles/gpu_rendering.html): CUDA/OptiX, HIP, oneAPI and Metal device routes, subject to hardware/platform requirements.
- [Blender volume object reference](https://developer.blender.org/docs/release_notes/2.83/volumes/): OpenVDB-backed volume objects and sequence rendering.

Next implementation milestone: a reviewed static render-bundle contract and one
public fixture imported/rendered in a pinned Blender version, before any product
button claims Blender support.
