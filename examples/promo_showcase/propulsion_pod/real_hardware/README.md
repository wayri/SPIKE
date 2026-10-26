# Selected real-hardware reference pair

Selected23 October2026: **OpenMotor CIAG_2_28 125_25** and **ENOLA Casalino300mm, collective pitch+5degrees**. These are separate openly documented hardware references composed for a restrained research pod. They have not been measured together. OpenMotor is oversized for this smaller blade; a shaft/hub adapter and load-envelope review remain necessary. A source bundle is not an executed full real-motor/CFD/thermal analysis.

## Exact motor source

[eMotres OpenMotor-Hardware](https://github.com/eMotres/OpenMotor-Hardware/tree/1e1e56d7cf64ea393793ca5c06189251f87b6e98), revision`1e1e56d7cf64ea393793ca5c06189251f87b6e98`, retained unmodified in`OpenMotor125_25/` with upstream README and CERN-OHL-W-2.0 license. STEP hash`0f6737f1ddba820376e88298cf05725de36048f03c227714bf391e7cf21b07d3`; PDF hash`256d463196d33f09f517cffaf355b43609f6a36383b98d46b3b72f1a23d9ba34`. Per-file hashes and source notices accompany the files.

FreeCAD1.1.3 native import finds internal stator teeth, core, magnets, coils, connectors and phase plates; root assembly has616solids and an approximately138.54mm diameter/53.5mm axial envelope. All1016 inspected shape-bearing objects are geometrically valid, including repeated assembly parents/datum objects. Do not sum all object volumes: parents repeat children. `STEP_NATIVE_INSPECTION.json` and original`inspect_step.py` retain the audit.

The datasheet supplies24slots/28poles,25mm lamination length,10turns,4parallel0.8x3mm wires, N52UH magnet grade and H070-20 stator steel. It does not supply phase R, phase/self/mutual/end-turn L, rotor J, vendor recoil curve, grain-oriented directional B-H/loss curves, thermal capacities/contact conductances or measured temperatures. Wire connectivity, signs/series-parallel allocation and material orientation must be independently extracted/reviewed. Geometric estimates may later be labeled as estimates with assumptions; they must not be relabeled measurements. An Arnold N52UH curve would be a supplier substitution until original magnet identity is established. H070-20 grain-oriented steel cannot silently become generic isotropic steel.

The17-row motor CSV used an unnamed**30x14inch propeller** at approximately76â€“81.3Vbus. Its shaft power and Q*omega differ by as much as5.60% in the published raw rows; preserve both channels and investigate before calibration. There are no temperature columns or stated uncertainty/test-date records. The selected VESC IRFS7530 devices are rated60V, so the75V motor/roughly80V test is not a compatible qualified board operating point. A proposed bus<=48V is a separate preliminary design assumption, not reproduction of those tests.

## Exact propeller source

Universitat PolitÃ¨cnica de ValÃ¨ncia, **ENOLA numerical and experimental propeller database**, v1, published10May2026, [DOI10.5281/zenodo.20111572](https://zenodo.org/records/20111572). Funding: ENOLA PID2022-142018OA-I00. Primary metadata explicitly licenses the dataset CC-BY-SA-4.0; exact metadata, license, original README/disclaimer and selected archive-directory records are retained in`ENOLA_Casalino30cm/`. The README traces the reconstructed Casalino geometry to DOI10.1016/j.ast.2021.106707 and describes manufactured/tested collective-pitch variants. Preserve this lineage and do not imply author endorsement.

Use the exact pair:

- `CASALINO_D30cm_pitch+5deg.stl`, SHA256`4659b1f740d6e2ea30819b7a2ce3cdddd54703600ff0d0919d0529ff1db62afd`.
- `Casalino_SLA_Pitch+5deg_exp_0_90_deg.csv`, SHA256`d31b1de94e9dc8f91510a3fdd68aca0693ad71eecadfc8aac5b61107c0cee8d9`.

The STL has35744triangles,17868exactuniquevertices, zero boundary/nonmanifold edges in the edge-incidence check. Native tip span300 matches the GeneralInfo0.3m diameter: interpret native coordinates as millimetres and multiply by0.001 for solver metres. STL embeds no units; confirm origin/rotation axis and hub seating before meshing. Edge closure does not prove no self-intersection, geometric quality, structural safety or CFD convergence. Baseline`Casalino_CAD.x_b` is Parasolid; retainedÂ±5degree STLs are distinct geometry cases. No Casalino chord/twist/airfoil tables are supplied; do not invent them.

The selected CSV uses semicolons, UTF-8 BOM, measured RPM, inflow angle/speed, thrust/torque, standard-deviation channels and coefficients. It contains785 parsed records, including317 blank/nonnumericRPM records and422positiveRPM records, with positive speed1559â€“5880rpm and torque0.00968â€“0.37906Nm. ZeroRPM rows include mathematically infinite nondimensional coefficients; keep the raw file unchanged and explicitly exclude such rows from finite-coefficient comparisons. Match geometry+5degrees, fabrication/material, measured inflow angle, speed and air conditions when joining a simulation; do not pool baseline orâˆ’5degree rows. Some baseline filenames imply0degrees while measured inflow is~15degrees, so trust declared measured columns only after review. Temperature/density/rig conventions must be established from original experimental documentation before quantitative validation. The existing Re<=0.1 creeping-flow solver cannot validate these full-speed air-propeller measurements.

## Reuse and remaining gates

Keep upstream notices and CERN license with verbatim motor source. Modified motor CoveredSource needs dated modification/source notices and CERN-OHL-W obligations; manufactured products have separate CompleteSource obligations under section4. Retain propeller attribution, source DOI/version, CC license and disclaimer; mark transforms/adaptations and preserve applicable CC-BY-SA terms. These third-party files are not relicensed as Apache SPIKE software. The dataset explicitly excludes operational/safety-critical use.

Full real physics still requires actual winding topology/material adaptation, qualified magnetic curves and losses, derived/validated R/L/J, thermal properties/boundaries, adapter mechanics, resolved high-Re rotating-blade CFD with load/domain/grid convergence, common-step power/thermal transfer and GUI verification. Existing synthetic three-phase/BEM/thermal and original low-Re blade tests remain separate numerical prerequisites. See`docs/validation/PROPULSION_POD_REAL_DATA_AND_REVIEW_20261023.md` and`source_inventory.json`.
