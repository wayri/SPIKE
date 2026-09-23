# Hybrid DC zone contact audit

The pinned MODULAR-BUS-NIB `/12Vout` study exposed two independent hybrid-mesh
conductance defects. This audit uses the retained board and exact R19.3 source,
J14.2/J20.2/J15.2 load pad anchors. It does not establish release validation.

## Evidence and repairs

1. The generic pad attachment loop included zone centroids already served by
   explicit pad-zone coupling. At zone sizes 1/.5/.25 mm, J14.2 gained 1/0/2
   such F.Cu links. These nodes were zone cells, not tracks or vias. Their
   widths remained the entire .85 mm pad width. Removing only J14's generic
   zone-centroid links changed its drops from 3.042/3.415/1.686 mV to
   3.386/3.415/3.402 mV, while changes at the other two loads were below .004 mV.
   Generic attachment now excludes zone-region nodes; track/via attachment is
   retained. Explicit pad-zone connectivity remains evidence-gated.
2. Zone-zone branches used the full grid-cell width even for partial shared
   copper faces, and point-only contact could carry finite conductance. They
   now use the positive shared polygon-edge length. The generic 1 micrometre
   branch-width floor is bypassed for these geometrically admitted zone faces.

For a shared face of length w mm through copper thickness t mm, cross-section
is w*t*1e-6 m2 and branch resistance is L*1e-3/(sigma*w*t*1e-6) ohm. This is
the existing branch-distance approximation with its geometric cross-section
corrected. The derivation and tests were independently authored from this
dimensional invariant; no external source implementation was used.

The helper assumes simple, non-overlapping clipped fragments. Collinearity
uses the existing mesh containment tolerance (default .0001 mm), without
increasing it. A stricter exploratory 1e-7 mm comparison exposed 3-5 nm seams
between imported clipped triangle rays and split zone connectivity; aligning
with the existing geometric tolerance restored every original zone component.
The helper does not merge overlapping polygons or establish a new tolerance
policy. Point-only projected overlap remains zero.

## Bounded board verification

After both repairs, each of the six retained zone polygons and the complete
hybrid graph has one connected component at all three levels. All zone branch
widths match their positive shared faces to relative tolerance 1e-7. Exact
terminal source/load excitation and material settings are unchanged.

| Zone size (mm) | J14 drop (mV) | J20 drop (mV) | J15 drop (mV) | Copper loss (mW) |
|---|---:|---:|---:|---:|
| 1 | 3.677829702 | 3.757726991 | 3.934739197 | 37.900986299 |
| .5 | 3.690637567 | 3.711742482 | 3.847435683 | 37.499385772 |
| .25 | 3.717621242 | 3.470178189 | 3.921918356 | 37.032392624 |

Maximum scaled linear residual was 1.79e-16. The last pair's maximum-load-drop
change is about 1.94%, but J20's individual drop still changes about 6.51%.
No convergence threshold was relaxed. These results do not prove that all
source-to-load paths have converged. The remaining single-point pad-zone
coupling, nonorthogonal cell distances, shared trace/zone conductor ownership,
and fourth-level behavior require further qualification. Knowledgeable human
review of numerical code is still required before release.

Reproduce the assertion-bearing first-three-level audit with:

```powershell
.venv\Scripts\python.exe scripts/audit_hybrid_zone_topology.py --output artifacts/hybrid-zone-audit.json --solve
```

The diagnostic exports cell-component counts, attachment endpoint origins,
face-width ratios, per-load drops, residuals, and copper loss. `--factors`
selects other levels explicitly. `--face-experiment` is an in-memory diagnostic
variant, not an alternate production solver. Focused tests are
`test_hybrid_pad_zone_coupling`, `test_hybrid_zone_face_width`,
`test_hybrid_mesh_containment`, and `test_hybrid_dc_terminal_validation`.
