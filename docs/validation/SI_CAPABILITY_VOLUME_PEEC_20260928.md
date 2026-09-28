<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI capability and finite-volume PEEC upgrade (2026-09-28)

## Native solver correction and cross-check

The active Python 3.12 native module was stale: source bindings already
contained `VolumeMatrixAssembler`, but the loaded `.pyd` exposed no volume
APIs. It was rebuilt from this repository's C++ sources with the installed
MSVC/Eigen/nanobind toolchain. The Python 3.14 module was rebuilt too for an
independent runtime check. `scripts/check_solver_qualification_environment.py`
now inventories the volume APIs to catch that deployment mismatch. This is a
development-runtime rebuild; a packaged desktop worker was not rebuilt or
released in this run.

`spike.peec_2_5d` now retries the bounded common-volume matrix only after its
legacy line-kernel partial-inductance matrix fails the positive-energy gate.
The retry applies no passivity projection or diagonal shift; failure remains
failed, with both the volume-retry and legacy nonpassivity diagnostics. An
explicit `peec_volume_extraction: disabled` preserves the old path; `enabled`
selects volume first. Successful retry remains `approximate` because the
single-reference C/G model, port/return geometry, and conductor AC losses are
not fully qualified.

On the provisional HForsten RF_IN slice, the volume run uses 31 field bases,
reports zero negative-energy modes, and returns a signal-path driving-point
impedance of 0.0707+j7.3277 Ω at 1 GHz and 0.1547+j22.8730 Ω at 3 GHz.
On the provisional Marble +1V0 slice, it uses 28 field bases, reports zero
negative-energy modes, and returns 0.0188+j0.4072 Ω at 100 MHz and
0.1110+j4.0034 Ω at 1 GHz. Both the explicit-volume and automatic-retry runs
completed; records, native-module hashes, assumptions, and quality diagnostics
are under `build/validation/internal-comparison/`. These are local
driving-point results, not full-board S parameters or calibrated SI channels.

The saved HForsten openEMS two-port can be converted to a differential
impedance by `Z=50(I+S)(I−S)⁻¹` and `Zdiff=Z11+Z22−Z12−Z21`. It gives
approximately j5.247 Ω at 1 GHz and j15.816 Ω at 3 GHz, versus the PEEC
signal-path j7.328 Ω and j22.873 Ω. The port current/return definitions are
different, and the openEMS board stackup, local return, and ports are
provisional. This discrepancy is **feedback for model work, not a calibration
factor**. No PEEC coefficient was fitted to it. The full complex comparison,
conditioning check, and plot are saved in
`build/validation/openems-internal-comparison-20260928/hforsten-crosscheck.json`
and `hforsten-openems-peec-crosscheck.png`.

## SI results and visualization

The loaded network backend now returns matched-reference per-port reflection
and VSWR, retaining explicit finite/infinite/non-passive statuses. The SI
views consume those returned samples and leave invalid VSWR points as gaps.
The loaded view also plots returned TDR reflection. Existing geometry-channel
views already plot S parameters, impedance, NEXT/FEXT, and eye results.
The field viewer admits actual finite three-component E/H vectors from an
`AnalysisResult` and rejects missing or nonfinite vectors.

`scripts/plot_si_capability_evidence.py` executed the public analytical
four-port coupled-RLGC workflow. Its result completed frequency and time
stages with NEXT/FEXT, per-port VSWR, TDR, and a receiver eye height of
1.7656 V. The plot and compact summary are under
`build/validation/si-capability-evidence-20260928/`. This is an
**experimental analytical reference**, not a board extraction or compliance
claim. The same directory holds the provisional native PEEC impedance plots.

The network workflow still returns `field_maps: unsupported`: neither the
analytical network result nor the current PEEC board result supplies spatial
E/H samples. The UI can display such samples when a field solver actually
returns them; it does not synthesize fields from S parameters. Four-port
board-level NEXT/FEXT and eye validation still requires qualified coupled
geometry, materials, return paths, port calibration, and independent measured
or trusted-tool correlation. Full-board issues remain as documented in
`PROVISIONAL_PI_SI_OPENEMS_INTERNAL_20260928.md`.

## Checks

- Native C++ `test_volume_inductance` and `test_volume_matrix`: passed.
- 48 focused Python SI/PEEC/environment tests after final integration: passed.
- The broader 100-test PEEC discovery ran with 16 environment errors because
  this Python 3.12 environment lacks optional Shapely; 14 tests were skipped.
  Python 3.14 has Shapely but its 88-test run has five import errors because
  that interpreter lacks `jsonschema`.
- SI channel, SI workflow plots, trace plots, TypeScript `--noEmit`, and the
  project architecture check: passed.
- Provisional source-backed HForsten and Marble default PEEC cases: completed
  with the volume retry and `approximate` status.

Numerical PEEC changes require knowledgeable human review before release.
