# SPIKE Third-Party Notice Register

This register is incomplete and is a release-blocking audit record, not a grant
of rights. Every distributed package must generate a version-specific notice
bundle and SBOM from verified artifacts.

| Component | Evidence in workspace | Current handling | Release action |
| --- | --- | --- | --- |
| FreeCAD SPIKE Workbench | `integrations/freecad/SPIKEWorkbench/LICENSE` | MIT component | Preserve copyright, permission, and warranty text; confirm contributors |
| sparseLizard native adapter | `integrations/sparselizard-native/LICENSE` and SPDX headers | GPL-2.0-or-later linked executable | Keep process-isolated; satisfy GPL source and notice duties or exclude from distribution |
| sparseLizard upstream source/runtime | `runtime/external/sparselizard/source/` | GPL upstream material | Do not place in proprietary package without complete GPL review and compliance |
| ngspice runtime | `runtime/external/Spice64/docs/COPYING` | Mixed component licenses | Produce component-level notice/SBOM; keep process-isolated; review redistribution |
| openEMS runtime | `runtime/external/openems-0.0.36/` | License evidence incomplete locally | Exclude until upstream licenses, source obligations, dependency notices, hashes, and SBOM are captured |
| OpenFOAM | external installation in `dependencies.lock.json` | Optional external process | Do not bundle by default; record exact distribution and adapter obligations |
| FloTHERM | customer-provided proprietary product | Optional connector | Never bundle or download; require customer entitlement and permitted API use |
| NumPy/SciPy and packaged Python dependencies | worker/package output | Multiple permissive and component licenses | Generate notices and SBOM from the final worker artifact |

## Asset Provenance Still Required

Commercial release also requires ownership or redistribution evidence for demo
boards, screenshots, help media, icons, fonts, 3D models, SPICE/IBIS models,
validation datasets, and reports. Absence from this table does not imply approval.

