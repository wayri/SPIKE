<!-- SPDX-License-Identifier: Apache-2.0 -->
# 0077: Native pad angle and reflection boundary

Status: Accepted for bounded source import and display transport.

## Evidence

KiCad 10.0.6 public native reads report that pad angles in saved board files
are absolute board angles: omitted is zero, independent of footprint rotation.
Local positions rotate with the footprint; back-side reflection is already
encoded in stored coordinates and custom primitives. The source fixture has
footprint angle 90 degrees and pad angle zero. The previous S02 assertion
incorrectly expected 90; that receipt remains in
`docs/validation/parity/WF01-S02-native-angle-failure.json`.

## Decision

Neutral legacy pad `rotation` uses mathematical counter-clockwise rotation in
numeric XY, consistently with existing DC, hybrid, thermal and quasistatic
consumers. KiCad board angles use the opposite sign in stored Y-down coordinates.
Normalize at import: `rotation=-native_angle`; retain `native_pad_rotation_deg`.
Do not add footprint angle or another back-side position/primitive reflection.
No vendor branch is added to numerical geometry consumers.

Direct TypeScript native preview retains native display angle. Normalized
snapshots negate neutral numeric angle when projecting to `ParsedPad`, whose
rendering convention is the inverse, including non-KiCad snapshots. Footprint
text/graphics and automatic model placement remain outside this decision.

## Acceptance and limits

Source-bound native facts cover 48 footprint/module, front/back, cardinal and
non-cardinal pose cases plus eight supported rectangular-anchor asymmetric-pad
and centered slot cases. Import and perimeter consumers recompute agreement.
Position tolerance is 1e-6 mm; bounding-box tolerance is 2e-6 mm for native
integer-grid rounding. Existing scalar/cardinal assertions keep 1e-9 tolerance.
Circular-anchor custom union remains explicitly unsupported.

Native ODB export works through `PCB_IO_MGR.Save` with absolute output path and
`str_utf8_Map`. Member bytes, original-source geometry, cutouts and references
are independently checked. Generated font data is excluded from the distributed
geometry archive; missing stackup/model assignments block solver readiness.
Observed XY reflection and reversible arc endpoint order are facts for this
fixture, not a universal 3D frame converter or directed-path qualification.

Old saved snapshots with incorrect geometry require reimporting original source;
no guessed migration is performed. Importer revision is `kicad-pad-frame-v3`.
This is not solver-accuracy or release qualification; knowledgeable human review
remains required before numerical use is released. Evidence uses public native
APIs and independently authored fixtures, not vendor implementation code.
