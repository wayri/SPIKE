# Solder connections on pins and terminals

Solder presentation adds editable 3D shapes to component-to-pad connections in the main viewport. Existing electrical and thermal bond properties remain separately editable.

## 1. Choose connections

Import the board and open **Solder connections & component bonds** from command search, or **Bonds** from the existing design controls. Use **Auto-connect** to review imported component/pad ownership, or select a pad in the viewport and use **Add bond**.

Every rendered joint must identify a unique owned pad: pad ID (or an unambiguous reference/pad-number pair), matching reference, pad number and net. Missing identities are not guessed from proximity. Pads without a named net may be drawn when both declared names are empty; this does not establish an electrical connection.

## 2. Model the solder

Select a connection row and choose **Enable solder visual**, or use **Model solder** to add defaults to eligible enabled connections together. The bulk action uses through-hole collars for drilled pads and SMD fillets for surface pads. Existing solder settings are retained.

| Control | Purpose |
| --- | --- |
| SMD fillet | Tapered rounded rectangular deposit around the declared pad |
| Through-hole | Annular collar on the exposed copper surfaces; preserves the drill opening |
| Terminal | Tapered terminal deposit/collar; preserves a drill opening when present |
| Height | Authored joint height, 0.01–20 mm |
| Spread | Authored lateral extension beyond the pad, 0–20 mm |
| Opacity | 0.05–1, multiplied by applicable layer/board display opacity |
| Show in viewport | Hide a joint while keeping its settings |
| Remove visual | Remove the display model while retaining the underlying bond |

Use **Validate** to review missing pad identities, unsupported drill geometry and malformed display settings alongside existing bond validation. Invalid visual records are omitted, rather than drawn on another pad. Through-hole style requires a plated drilled pad. Geometry is a simplified authored profile and may overlap an imported pin model; it is not a source CAD solder solid or a measured wetting surface.

## 3. View and save

Use the existing **3D** viewport. Shapes follow board placement, top/bottom side, applicable layer visibility and opacity, exploded display, net isolation, translucent scene mode and section planes. They do not add a new render window or toolbar.

In multiboard projects, select the owning board before enabling/editing the solder geometry. SPIKE binds a record only when that occurrence contains the exact declared pad identity. The occurrence is shown in the editor. Unscoped older records are displayed only in single-board views; explicitly scoped records do not attach to same-named pins on another board. Editing an unscoped solder record while its uniquely matching board is selected binds it to that occurrence.

The current display budget is 2,000 joint surfaces per main viewport. A through-hole pad with two displayed surfaces uses two entries. Identical profiles and opacity values are instanced together. Joint meshes do not replace the authoritative selectable pad underneath. The existing renderer owns and disposes their resources.

Use ordinary **Save**. Connection identity, occurrence, style, dimensions, opacity and visibility survive native `.spike` save/open and Save As, and are included in project backups.

## Model and analysis boundaries

Solder visualization is presentation geometry. It does not infer reflow, wetting, voids, fatigue, yield, mechanical strength, manufacturing acceptability or electrical continuity. It is not automatically included in a volume mesh, geometry export or solver domain. Free-standing terminals without an owned PCB pad require a separate geometry/identity workflow.

Changing display height/spread does **not** calculate resistance, thermal conductance or contact area. The existing bond's electrical resistance/current limit and thermal conductivity/contact area remain explicit independent analysis inputs. Validate those values using the applicable method and engineering evidence before analysis.
