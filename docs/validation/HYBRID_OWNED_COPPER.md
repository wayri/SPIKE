# Opt-in pad-owned hybrid DC copper

`AnalysisSpec.mesh.pad_zone_coupling = "owned_shared_faces"` selects an
experimental DC-only discretization. The default hybrid route is unchanged.
This opt-in remains **approximate**, including when terminal mapping and
linear residual checks pass. A four-level per-load study is still required.

The implementation uses existing pad cells as the unique owners of their
copper. Each convex pad outline is subtracted from intersecting zone cells;
the pad's enclosed drill void is also removed from zone copper. Pad metal is
not counted again as zone metal. Convex half-plane differences and polygon
triangulation require no additional geometry dependency.

The convex hull of generated pad cells must agree with the authoritative
admitted outer polygon and drill area within 1e-8 mm2. Roundrect pads retain
their imported corner radius. Pad-grid duplicate cleanup uses 1e-10 mm so
retained short arc segments are not simplified away by containment tolerance.
Zone fragments are convex-partitioned before area-centroid placement. Where a
straight centroid link would leave retained copper, two half-links pass
through the actual shared face; the area of the cells remains unchanged.

Pad-pad and pad-zone conductance use positive shared boundary length as width,
existing copper thickness and conductivity, and physical branch length. A
finite contact footprint is represented by all of its faces, not one closest
pad/zone node pair. Exact terminal weights still use pad-cell `node_id` and
physical area. Source-filled solid/thermal connectivity evidence gates every
pad-zone interface; explicit `none` does not acquire a contact.

For a branch with width w mm, thickness t mm and length L mm,
R = L*1e-3/(sigma*w*t*1e-6) ohm. Positive-area polygon differences conserve
admitted zone area. Shared-face stamping conserves current because each
resistive link contributes equal/opposite nodal current and nonnegative
I-squared-R loss. The independently authored radial annulus oracle is
R = ln(r_outer/r_inner)/(2*pi*sigma*t); a .5/.25/.125 mm pad refinement reduces
error and ends below 1% relative resistance error. Its exact continuum
half-cell electrode resistances isolate the production interior radial mesh
from terminal-snapping error. No external source implementation was used.

Unsupported cases fail closed with an empty conductor graph and an error:

- Missing/invalid retained filled polygons, explicit unresolved holes, or
  incomplete source-fill provenance.
- Missing solid/thermal evidence for a positive pad-zone face, or retained
  connected-contact evidence without a reconstructed positive face.
- Unsupported/custom/chamfered pad shapes, unsupported/off-center drills,
  overlapping pad ownership outlines, or a zone fully absorbed by pad/drill
  masks. Overlapping same-net pads can be valid source geometry; this route
  currently does not reconcile their ownership and reports them unsupported.
- Outer/void area mismatch or failure of the 1e-8 mm2 zone partition balance.
- A non-DC analysis requesting this route.

Known remaining approximations include nonorthogonal branch distances, the
existing angular landing of plated-pad barrel branches, and trace/zone and
via/zone overlaps that are not repartitioned by this pad-specific route.
These limits prevent a general conductor-accuracy or release-validation claim.
Knowledgeable human review of the numerical change remains required.

## Bounded real-board evidence

MODULAR-BUS-NIB `/12Vout`, exact R19.3/J14.2/J20.2/J15.2 anchors, 10 A total:

| Zone cell (mm) | J14 drop (mV) | J20 drop (mV) | J15 drop (mV) | Copper loss (mW) |
|---|---:|---:|---:|---:|
| 1 | 1.225253162 | 1.283116376 | 1.441636041 | 13.166685274 |
| .5 | 1.120302226 | 1.169713843 | 1.318510436 | 12.028421684 |
| .25 | 1.069779336 | 1.112083309 | 1.262462415 | 11.481083532 |

All levels retain six zones, one component per zone and one global conductor
component. Pad metal area is 47.0992899403 mm2 and admitted pad drill-void area
is 10.6638523046 mm2 across the six layers. J20's shared contact perimeter is
1.07542663504 mm per layer, even though its face count grows from 13 to 14 to
16. Maximum observed current imbalance is 1.27e-8 A and scaled linear residual
is 1.44e-16. The last per-load changes remain approximately 4.4-5.2%, so these
three levels do not demonstrate the required 3% per-load convergence.

Reproduce:

```powershell
.venv\Scripts\python.exe scripts/audit_hybrid_zone_topology.py --owned-shared-faces --solve --output artifacts/hybrid-owned-copper.json
```

The JSON includes pad/zone face counts and cross-sections, area ownership,
component counts, terminal drops, KCL, copper loss and load power deficit.
Focused tests are `test_hybrid_owned_copper` plus the existing hybrid contact,
zone-face, containment, and exact-terminal suites.

## Short-face topology regression

At zone cell .0625 mm (factor .125, 12 GiB admission budget), the former
face routine discarded edges shorter than the .0001 mm containment band.
Three real F.Cu triangles therefore had no zone neighbors; one had no other
conductor attachment. Their areas were 6.8633424593e-10, 2.0457137164e-9 and
6.4536322362e-10 mm2, all above the existing positive-area cutoff. The first
triangle has vertices (158.542517556851,75.6225),
(158.5425,75.622578184208), (158.5425,75.6225) mm. Its three real boundary
faces measure 1.7556851020e-5, 7.8184207993e-5 and 8.0131226106e-5 mm.

Edge degeneracy now uses a separate 1e-12 mm arithmetic threshold. When
either edge is shorter than the containment band, collinearity uses the
stricter 1e-10 mm clipping cleanup scale, preventing the broad containment
band from turning a short point contact or clearance into conductance.
The positive admitted-face threshold remains 1e-7 mm. No copper is removed
and no distance tolerance is widened. Midpoint routing and the independent
audit helper use the same distinction; analytic rectangle/triangle tests
check real short faces in both argument orders, point contact and clearance.

The complete mesh-only rebuild retains 170,524 nodes and has 338,437 branches
(22 added). Its global component contains all nodes. Each of six zones has
one component, with node counts 25,867; 28,289; 28,289; 28,289; 28,289; 26,116
for F.Cu, B.Cu and In1.Cu through In4.Cu. Zone area balance is unchanged at
+3.1832314562e-12 mm2; pad metal and drill-void areas are unchanged. The mesh
reports no issues. This verifies geometry and connectivity only; a fresh DC
solve and convergence qualification remain separate requirements.
