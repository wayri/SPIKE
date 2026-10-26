<!-- SPDX-License-Identifier: Apache-2.0 -->
# Mechanical viewport tools

The development viewport has a compact **Mechanical objects, sections and dimensions**
icon at its upper-right when a SPIKE project contains mechanical parts. The layer
selector remains at the left. Hover previews the mechanical controls; leaving hides
that preview. Click the icon or interact with its panel to pin it. Close, Escape or
an outside click dismisses it. Closing retains measurement and angle drafts for the
current loaded assembly.

Use the compact **Objects**, **Section** and **Measure** tabs; switching tabs retains inputs.

## Object management

| Control | Effect |
| --- | --- |
| Object name | Select the exact part occurrence and switch to 3D |
| Eye | Show or hide that occurrence |
| Translucency | Toggle opaque/20% context; the slider accepts any opacity from 0–100% |
| Isolate | Inspect one mechanical part; Restore complete assembly ends mechanical-part isolation. Board context remains visible. |
| Show all / Hide all | Change visibility of every mechanical occurrence |
| Translucent | Show all mechanical occurrences at 20% opacity |
| Reset display | Restore each part's source visual settings |
| Find object | Filter names, types and IDs, with `*` and `?` wildcards |
| Placement, hierarchy and materials | Open the existing transactional MCAD editor |

Visibility and opacity update retained meshes and exact-selector previews. They do
not reload the source geometry or change transforms, material properties or solver
inputs. Opacity drags record one undo start per pointer/keyboard gesture. Display
overrides and section settings are saved in `.spike` projects and restored on open;
Reset removes the overrides. Isolation and the current measurement are temporary.
Hidden/missing STEP tessellations still need the existing visual-preparation workflow.
A listed object does not establish that it has renderable geometry.

## Cross section

Choose **Section** inside the same control. Use XY, XZ, YZ or a 45-degree
bisector preset, or enter azimuth/elevation in degrees and Apply. Arbitrary entered
angles are supported; random angles are not chosen automatically.

- Azimuth runs from +X toward +Y; elevation runs from the XY plane toward +Z.
- Offset is the signed distance in assembly millimetres along the unit normal.
- **Through selection** places the applied plane through the selected part origin
  and enables it. The origin is an explicit anchor, not a picked face centre.
- Enable section and First plane enabled control application; Flip retained side
  reverses the kept half-space.
- **Box / multiple planes** opens the existing advanced controls for up to six
  arbitrary planes or six box bounds. Enabled planes retain their intersection.
- Isolate an object before sectioning to inspect that part; restore the assembly
  to inspect the assembled scene. These use the same main viewport and camera.

These are visual, uncapped cuts. They do not generate closed section solids,
BREP profiles, engineering drawings or a new solver mesh. Exact section curves,
capped cut faces and dimension snapping to native CAD topology require a separate
geometry-kernel workflow; they are not claimed by this control.

## Dimensions

Choose **Measure**. Enter both XYZ points in assembly millimetres, or select
an object and use **Set A/B from selection** to capture its transformed occurrence
origin. The panel displays distance and signed ΔX/ΔY/ΔZ (B minus A). A line and
endpoint markers appear in the 3D viewport. Clearing removes them. JSON and CSV
export retain the numeric measurement; coordinate entry and anchor capture are
not surface snapping, minimum-clearance computation or tolerance inspection.

The current measurement is a session tool, not a persisted CAD annotation. It is
cleared on assembly replacement; hiding the mechanical control retains its inputs.

See also [UI navigation](UI_NAVIGATION.md), [mechanical export](MCAD_EXPORT.md)
and [MCAD materials](MCAD_MATERIAL_WORKFLOW.md).
