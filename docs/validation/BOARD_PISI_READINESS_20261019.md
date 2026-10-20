<!-- SPDX-License-Identifier: Apache-2.0 -->
# EBrake1 and Marble board SI/PI audit, 2026-10-19

The later [PI01-S01 verification](PI01_OWNED_PAD_DC_20261019.md) records the
actual EBrake owned-pad repair, unchanged default acceptance failures, and
fresh coarse/refined Marble RT0 replays. It preserves the limitations below;
bounded geometry-stage completion is not full-board qualification.

Neither board is qualified for full-board SI/PI. This audit uses the actual
complete imported boards and public CLI paths, without replacing copper,
ground planes, materials, or terminal coordinates with a synthetic fixture.
Generic import `solver_readiness` flags are not solver-specific admission.

Inputs are pinned to:

| Board | Local source | SHA-256 |
| --- | --- | --- |
| EBrake1 | `app/public/demo/ebrake1.kicad_pcb` | `d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca` |
| Marble | `build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb` | `3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512` |

The imported designs contain respectively 787/37,380 tracks, 103/3,664 vias,
489/5,272 pads and 27/124 zones. Both import reports mark general SI/PI readiness
true; the individual solver results below impose narrower requirements.

Reproduction from the repository root:

```powershell
build/qualification-py311/Scripts/python.exe scripts/check_board_pisi_readiness.py --output-dir build/board-pisi-20261019-audit
```

Use a new output directory for a new run. The retained local folder contains
complete v1/v2 imports, requests, CLI outputs, command arrays, hashes and
`readiness.json`. Exit zero means that the audit commands produced evidence,
including expected unsupported states; `full_board_pisi_ready` and
`production_qualified` remain false. The local native binary SHA-256 was
`2f92fe0b3fb53df8e127d82b6b650c75dc0aa2fe57c56826a3b63e3443dadafc`.
The Marble source and native runtime under `build/` are local dependencies,
not a clean-machine or redistributed qualification package.

## Actual-board observations

DC uses an explicitly assumed 1 V source and 1 A load, without contact/package
resistance or a represented return conductor. Nominal operating currents and
voltages are unknown. These are supply-conductor sensitivity probes, not
complete operating-point, regulator, transient-load or PDN studies.

EBrake selects the complete `Net-(U2-VBUS)` net, from U2.40 at
(167.575, 47.295) B.Cu to TP1.1 at (164.15, 47.325) B.Cu. Its two tracks and
two pads are retained. Public DC results at 0.5/0.25/0.125 mm are
1.548301728/1.367260970/1.407008460 mOhm. Consecutive changes, relative to
the finer result, are 13.2411% and 2.8250%: the frozen two-step 2% gate fails.
Scaled residuals are at most 8.42e-17, and single-load power-balance error is
at most 3.52e-17 W. These algebraic checks do not establish spatial accuracy.
Two additional fixed-budget public CLI probes at 0.0625 and 0.03125 mm both
block at the configured 2,000-branch cap, with custom-pad grid coarsening also
reported. The cap and convergence criterion were not relaxed. Their exact
commands and issues are retained in `ebrake-extra-refinement.json`.

EBrake public AC completes as `approximate` at five points from 1 kHz to
1 MHz, with capacitance explicitly disabled and no return net. The legacy
partial-inductance matrix fails the energy gate; the automatic bounded volume
retry succeeds without projection. Reported partial L is 1.76239 nH and R
at 1 kHz is 2.49397 mOhm, which is materially different from the 0.5 mm DC
result. This is an unqualified partial R/L driving-point diagnostic, with no
DC/AC agreement or AC refinement claim.

Marble selects `Net-(C383-Pad1)`, U37.18 at (232.9726, 159.4734) B.Cu to
R195.1 at (233.0832, 159.385) F.Cu. Public DC at 0.5 mm completes as
`approximate`, giving 4.169115349 mOhm and a 7.09e-17 scaled residual.
Public AC fails: the legacy matrix has eight negative-energy modes, and
the volume retry rejects four zone bases outside authoritative copper
(`PEEC_ZONE_BASIS_OUTSIDE_COPPER`; one extends 0.03630054 mm2 outside).
No passivity projection, geometry clipping, or capacity increase is used.

Both public transient probes fail with `PEEC_MATRIX_EXTRACTION_FAILED` /
`PEEC_INDUCTANCE_GEOMETRY_UNSUPPORTED`, requiring finite-volume extraction
for singular or unrepresentable line interactions. Each uses the same DC
terminals and 0.5 mm mesh, a constant source, `step,0,2e-6,1e-6` load,
8 us stop, 8 ns timestep, manual output decimation 25, capacitance `none`,
and a 60 s solver limit. The common CLI flags are:

```text
analyze-transient <design-v1.json> --net <net> --source <x,y,layer,1> --load <x,y,layer,1> --mesh-size-mm 0.5 --max-zone-cells 1000 --max-conductors 2000 --source-waveform constant --load-waveform step,0,2e-6,1e-6 --stop-time-s 8e-6 --time-step-s 8e-9 --output-decimation 25 --output-decimation-mode manual --capacitance-model none --max-solver-time-s 60
```

EBrake strict geometry SI on the actual straight 1.3 mm `Net-(U3-BEMF)`
trace rejects multiple GND reference zones on In2.Cu. The projected-footprint
helper finds coverage in zone `e8137e8d-5840-5dc3-affe-0d1e3c038235`, but
the unchanged full design remains ambiguous under the current contract.
A read-only exploratory clone selecting that zone encounters a second blocker:
imported copper conductivity is absent. That clone is not a board result and
was not used to generate S parameters. No copper value or reference polygon
was fabricated. Marble strict SI on `/WhiteRabbit/SI570_CLK_N` rejects bends.
Both SI probes use a diagnostic 50-ohm, DC-through-64-MHz uniform grid, not a
reviewed signal specification. Neither produces an admitted board SI channel.

## Corrected Marble topology gate

The historical statement that C383.1 is disconnected is superseded. It arose
from former incorrect backside-pad placement; the corrected importer puts the
pad in the actual stored copper. The initial current-source audit was retained
as `marble-current-rt0.json`: it blocks all three levels on the obsolete
isolation predicate. This is not a physical loss of convergence.

The new independent oracle reads native source expressions, without using
the importer, mesher or pad-outline helper. C383 has footprint position
(234.9284, 157.988), no rotation, and pad 1 local position (-0.45, 0), size
0.62 x 0.62 mm. Its center is (234.4784, 157.988). The same simple stored
78-vertex net-656 B.Cu filled polygon fully covers its 0.3844 mm2 pad and
contains U37.18's center. U37's footprint at (232.9726, 161.8234, 180 deg)
and pad local position (0, 2.35) independently give (232.9726, 159.4734).
The former mirrored C383 center at x=235.3784 lies outside this copper.

`audit_peec_rt0_refinement.py` now pins the native board hash, records this
source geometry proof, and requires both R195.1 and C383.1 to be connected
to U37.18. Its report contract is v2; old isolation-only rows cannot pass.
The 2% resistance, nonworsening trend, residual, KCL, energy and resource
thresholds are unchanged. Disconnected-network rejection remains covered by
the separate manufactured kernel regression, not a false real-board assertion.
The public CLI's retained `marble-disconnected-dc` case name is the legacy
probe identifier: its completed result now correctly demonstrates C383
connectivity, not isolation.

The corrected current-source rerun command is:

```powershell
build/qualification-py311/Scripts/python.exe scripts/audit_peec_rt0_refinement.py --board build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb --sizes 0.5 0.25 0.125 --max-unknowns 250000 --max-triangles 250000 --interior-edge-factor 0.25 --output build/board-pisi-20261019-audit/marble-corrected-rt0.json
```

The corrected rerun passes this narrow DC gate. Resistance at 0.5/0.25/0.125 mm
is 4.196854930/4.140156100/4.108869814 mOhm. Consecutive changes are
1.36949% and 0.761433%, below 2% with improving trend. Maximum relative
residual is 2.702e-10, cell KCL error 8.868e-12 A, face KCL error 3.801e-11 A,
and relative energy error 1.146e-11. The three systems contain
95,058/113,513/173,035 triangles and 60,684/71,052/104,261 factorized global
unknowns. C383.1 and R195.1 remain connected to U37.18 at every level.

The corrected report SHA-256 is
`632a7880b252514f86d4a58ac4db384c3336cd901ee0b76ed1f745273d170e4b`.
All four source hashes in that report matched the current files after execution.
The historical report remains preserved at
`build/validation/peec-rt0-condensed-fine-20260928.json` (SHA-256
`7c3acf2ba745b605b1182bb09ec1346d2f0b8a8390d12c879be7c067daf821a1`);
its old source geometry and isolation predicate are superseded, rather than
silently reused as current evidence. The corrected sparse experiment remains
DC-only, experimental, and separate from the production DC/AC mesh. It does
not establish AC L/C convergence, complete field extraction or measured accuracy.

## Verification and remaining work

The focused board evidence, RT0 audit and conforming-DC tests pass (22 tests),
including the actual pinned native-source oracle, rejection of old topology
evidence and manufactured disconnected-network rejection. The architecture
guard passes. This audit does not run or claim a full repository suite.

Physical closure still needs a convergent DC discretization for each selected
path; compatible current bases and field extraction for AC/transient; explicit
reviewed conductor materials, references and ports for SI; and independent
field/measurement correlation. Importer readiness, algebraic residuals, narrow
mesh trends and successful diagnostic execution are separate evidence.
