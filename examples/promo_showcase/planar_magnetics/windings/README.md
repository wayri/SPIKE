# Original planar winding candidate projects

Three original, editable KiCad 10 projects contain real routed copper, plated terminals, explicit stackups and native schematic diagrams:

- `primary/primary.kicad_pro`: 44×38×0.8 mm, four 70-um copper layers, two turns per layer in series, three deliberately separated through-via transitions. Nominal core-window linking is eight turns. The alternating mirrored paths retain current sense.
- `secondary/secondary.kicad_pro`: 50×50×0.8 mm, four 70-um copper layers, one turn per layer in parallel, 2.5-mm winding traces with 2-mm external leads/buses. Each terminal uses a 16-pin 2.54-mm Berg-style bank. Nominal core-window linking is one turn. This is geometry, not a validated 27.8-A design.
- `aircore_inductor/aircore_inductor.kicad_pro`: 40×34×0.8 mm, two 35-um copper layers, four-turn 1-mm front spiral and a separate back-layer return. No inductance or saturation/current rating is asserted.

All boards use origin (0,0) at their outline center. Exact `.kicad_pcb`, `.kicad_sch`, project-local symbol library and library table are in each directory. The schematic L1 is explicitly **on_board=no**, representing the routed winding rather than another fitted component. P1/P2 and S1/S2 label physical winding ends. The PCB uses one continuous winding net per board because the copper itself is the inductive element. Therefore these are winding-equivalent diagrams, **not a direct schematic-to-PCB net synchronization design**; PCB/schematic net parity is not claimed and the two endpoint labels must not be used to re-net the existing continuous winding through Update PCB.

## Frozen mechanical and pin contract

Primary J1 pad1=P1 at(-20,-1.27) mm; pad2=P2 at(-20,+1.27) mm. Secondary J1 is S1, 16 parallel pins at x=-8.89,-6.35,-3.81,-1.27,1.27,3.81,6.35,8.89 mm and y=20/22.54 mm. Secondary J2 is S2, the same x values at y=-20/-22.54 mm. Both banks use 1-mm drill/1.8-mm pads. A 3×5.54-mm oval NPTH centered(-20,0) clears both primary terminal pins through the secondary board without overlapping holes. Berg-style pins/headers are mechanical placeholders and are not selected or qualified for the output current.

Each transformer PCB has three chamfered core-leg slots: center7.05×21.05 mm, and outer3.875×21.05 mm centered x=±14.2875 mm. These use the TDK ELP32/6/20 half-core envelope (nominal center6.35×20.35 mm, outer3.175×20.35 mm) plus0.35-mm edge allowance. Slot corners have0.2-mm chamfers. The official TDK drawing's URL/hash is retained in the core source manifest; its PDF is excluded from redistribution. Native geometry closure is not tolerance-stack or manufacturing approval.

Assembly placement contract is primary PCB z0..0.8 mm, secondary z1.0..1.8 mm, with a nominal0.2-mm inter-board geometric gap. The assembled STEP includes two core halves and original pin solids; it does not include spacers or insulating film. Clearance, creepage, insulation system, clamping, actual core seating and thermal expansion remain unqualified. The 48V→1.8V50W isolated converter and approximate27.8-A output are design targets, not demonstrated PCB capabilities.

Geometric polarity: **P1 and S2 have the same dot sense**. A separate closed-polyline post-linkage check records center/left/right winding numbers9/1/1 for the primary, equivalent to8/0/0 after a common whole-core loop is removed; secondary is-1/0/0 for S1→S2. Equal outerpost linking makes this reduction independent of the return-flux branch split. This is topology evidence, not magnetic FEM or a performance prediction. The terminal/external connection path belongs to the winding assembly contract.

## Stackup and gates

Transformer stackup, top to bottom:0.01-mm mask,0.07-mm Cu,0.17-mm FR4,0.07-mm Cu,0.16-mm FR4,0.07-mm Cu,0.17-mm FR4,0.07-mm Cu,0.01-mm mask (0.8 mm total). FR4 relative permittivity4.2/loss tangent0.02 are supplied illustrative material metadata, not a material lot qualification. The inductor uses0.035-mm top/bottom Cu,0.71-mm core and0.01-mm masks.

Native KiCad10.0.6 parsed all three final projects. DRC: **zero violations, zero unconnected items on all three boards**, without adding task-specific exclusions or suppressing findings. ERC: **zero violations on all three schematics**. Native schematic netlists and SVGs were exported. Board copper/outline SVGs and schematic SVGs were visually inspected. An independent same-layer segment/via overlap check found no unintended overlaps in the series primary or air-core winding; minimum separated track-edge gaps were0.6/1.0 mm respectively. This strengthens same-net winding checks beyond DRC, which cannot establish turn identity on its own. The parallel-secondary topology was reviewed from native layer exports. No native schematic parity, fabrication, dielectric withstand, contact resistance, skin/proximity loss, magnetic loss, efficiency, temperature, EMC or converter-control gate is marked complete.

## STEP and evidence

`output/promo-planar-magnetics-20261023/windings/` retains exact native DRC/ERC JSON, netlists, per-layer SVG, SVG review PNGs, closed-path linkage and independent overlap reports, generator/source scripts, and hashes in `verification.json`.

For parent assembly use **primary-board-copper.step** and **secondary-board-copper.step**: native board body, tracks, vias and pads with **components omitted**. Parent-owned header solids avoid double-counting stock header models. `primary.step`, `secondary.step`, `aircore_inductor.step` additionally contain the referenced stock header model. STEP uses native KiCad export coordinates: X is PCB X and Y is -PCB Y. Normalize the actual board-body z extent before applying assembly z placements; do not rescale the native geometry. The parent core assembly owns the final checked body/slot/header fit.

Board-only body XY bounds: primary[-22,22]×[-19,19] mm; secondary[-25,25]² mm; inductor[-20,20]×[-17,17] mm. The native boards reference standard installed KiCad header STEP models through KICAD10_3DMODEL_DIR; those library files are not copied into these source projects. Board-copper STEP exports are sufficient for portable parent assembly.

Reproduction requires KiCad10's Python and `kicad-cli`, plus the repository Python environment for the independent Shapely overlap check. Run the source scripts in the output directory only when deliberately regenerating candidates; generator UUIDs may change, so rerun validation and refresh parent source bindings after regeneration. No app/solver source was changed.

Original winding geometry and custom schematic symbols/scripts are SPIKE-owned Apache-2.0 material. Credit SPIKE/Yawar B(wayri) and contributors; retain repository license/notices. TDK data is reference material, not an endorsement. Standard KiCad library 3D models retain their upstream license/exception; these source projects refer to the installed library, while the parent uses independently authored header solids.
