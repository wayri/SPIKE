<!-- SPDX-License-Identifier: Apache-2.0 -->
# Provisional openEMS and SPIKE PI/SI experiment (2026-09-28)

## Scope and reproducibility

The runnable cases are local source-board slices, not full-board solutions or
accuracy benchmarks. HForsten VNA2 uses its three F.Cu `/filter_bank/RF_IN`
tracks and C5.1/U13.8 pads, plus an assumed 5 × 4 mm In1.Cu return plane,
FR-4 properties, and two uncalibrated 50 Ω vertical ports. Marble uses the
source +1V0 U4.6–C53.1 pads and two tracks, the imported near-surface design
stackup, and an assumed 3 × 2 mm In1.Cu GND rectangle. Source-board hashes and
case assumptions are in the generated JSON files. The synthetic returns and
unreviewed ports are explicit user-authorized exploratory assumptions.

`scripts/run_openems_provisional_hforsten.py` reconstructs the HForsten two-port
case. Port 1 and port 2 were excited separately, because the adapter allows
one driven port per run. Both jobs completed on a 0.2 mm requested mesh over
1–3 GHz with 11 samples. Raw normalized results and execution records are:

- `build/validation/hforsten-rf-in-2port-p1-20260928/engine-output/normalized-result.json`
- `build/validation/hforsten-rf-in-2port-p2-20260928/engine-output/normalized-result.json`
- Corresponding `*-execution.json` files beside those case directories.

`scripts/compare_provisional_openems.py` checks that the frequency grids and
run status match, assembles the complex two-port S matrix, and saves
`build/validation/openems-internal-comparison-20260928/two-port-summary.json`
and `openems-two-port.png`. Over the sampled band, |S21| is 0.99694–0.99741;
the maximum singular value is 0.999163, below the passive-network bound of
1, and maximum |S21−S12| is 0.000624. These checks detect gross numerical
inconsistency; they do not verify port calibration, mesh convergence, geometry,
materials, or board-level correctness. The sampled S matrix remains
`approximate`.

Native SPIKE scripts in `build/validation/internal-comparison/` reconstruct
the same local slices for routed DC PI and test native PEEC AC extraction.
`hforsten-internal.json` gives 1 A signal-copper drops of 3.0307, 2.7064, and
2.7574 mV at 0.2, 0.1, and 0.05 mm target meshes. `marble-internal.json`
gives paired +1V0/GND load-loop drops of 2.2743, 2.4040, and 2.3880 mV at
the same meshes. At 0.2 mm the Marble load signal drop is 1.6020 mV and the
return rise is 0.6723 mV; their sum agrees with the 2.2743 mV loop drop and
1 A power balance. The earlier use of a whole-mesh maximum supply drop as if
it were the load endpoint was corrected in the saved report. Both DC mesh
sequences are nonmonotonic and remain `approximate`. The saved
`internal-dc-mesh.png` plots these distinct terminal quantities.

## Incomplete AC and full-board work

The initial native PEEC AC attempts produced no valid S network. HForsten's
then-loaded native module lacked the finite-volume API and its standard partial-inductance
route rejected three negative-energy modes. Marble's combined pad/track
partial-inductance matrix has a −8.19 pH minimum eigenvalue and three negative
modes. Tracks-only and pads-only blocks are positive; the mixed interactions
cause the rejection. A plausible numerical cause is the mix of rectangular
self terms and line-integral mutual terms for conductors that overlap at the
pad/track joints. The
positive-energy gate correctly rejected the matrix. No passivity projection,
arbitrary fitted correction, or native SI S-parameter claim was made. A
qualified common-volume extraction and convergence checks are needed before
altering this numerical code; knowledgeable human review is required before
release. A later native-module rebuild and automatic finite-volume retry
completed approximate local driving-point results without producing a matched
SI S matrix; see `SI_CAPABILITY_VOLUME_PEEC_20260928.md`.

Marble openEMS 100 MHz–1 GHz jobs were prepared and admitted, but the first
excitation timed out twice at 300 s. The initial 0.15 mm mesh estimated
491,832 cells. A second 0.25 mm mesh estimated 109,074 cells, yet the generated
grid contained roughly 3.8 µm XY spacing near its curved pad. Its FDTD time
trace advanced only 0.167 ns in 300 s, far short of a 100 MHz cycle. The
failed execution records are
`build/validation/marble-pi-2port-p1-20260928-execution.json` and
`build/validation/marble-pi-2port-coarse-p1-20260928-execution.json`. Port 2
was prepared but not launched after these failures. No Marble openEMS spectrum
or cross-solver PI AC comparison is available.

The DC milliohm quantities cannot be compared numerically with 50 Ω
S parameters; the terminal definitions, excitation, frequencies, and physics
differ. Full Marble modeling still lacks translated via and drilled-pad
copper/hole topology. White Rabbit still has unfilled zone records. White
Rabbit, HForsten, and Haasoscope lack physical stackups. All four need reviewed
signal/return port planes for board-level frequency-domain claims. See
`OPENEMS_BOARD_COMPARISON_20260927.md` for the board admission blockers.
