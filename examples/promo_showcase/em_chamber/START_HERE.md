<!-- SPDX-License-Identifier: Apache-2.0 -->
# Virtual PCB in the SPIKE EM chamber

This explicit example uses the original SPIKE planar-patch KiCad teaching
board: RF on F.Cu, GND on B.Cu, one explicit 50-ohm aligned pad-pair feed.
The retained seven-frequency EMerge FEM run covers 3.0–4.2 GHz and returns
actual S11 and sampled complex angular fields/relative radiation patterns.
The board, screen assumptions, saved chamber settings and executed results
are included. No third-party board license or component model is required.

**Delivered:** native virtual chamber project, registered EMI risk screen,
executed unvalidated relative radiation pattern, GUI Python templates and raw
evidence. **Not delivered:** physically meshed chamber EMI, calibrated emissions
or radiated-immunity response. The current chamber is visual; its absorbers,
receive antenna, floor, table, polarization and turntable controls do not enter
the EM solve. No receiver reading or regulatory pass/fail is computed.

## Open and record the actual UI

1. File > Open `virtual-em-chamber.spike`. It retains the actual source board,
   EM setup, preflight, screening and chamber settings. Open **EM > Chamber** if
   the saved chamber-open preference is not applied by your build.
2. **Auto-place DUT**, **Inspect DUT**, then **Fit chamber**. Demonstrate flat,
   upright and side orientations, turntable azimuth, cutaway and absorber floor.
   Label this clip “Virtual test placement — chamber is not EM meshed”.
3. In EM's EMerge radiation panel choose **Open saved radiation result** and
   select `radiation/admitted-result.json`. The actual frontend admission helper
   accepted all seven patterns for this board and rejected an unrelated board.
   Select a frequency; inspect S11, cuts and angular probes, then **View radiation
   on bench**. These are normalized unvalidated radiation results. Changing
   chamber graphics does not rerun or change the field solution.
4. Tools > Python workspace: open `01_emi_screen_gui.py`, Run with Ctrl+Enter.
   This executes registered `emi_preflight` and `emi_screen` against the selected
   pinned board. It does not perform a field solve. One candidate net provides
   no comparative ranking: a zero normalized score does not mean low emissions.
5. Follow `radiation/README.md` for the **executed** GUI result replay and the
   optional fresh EMerge run template. Choose the separately installed EMerge
   interpreter and existing extension trust controls to rerun. Runtime binaries
   are not bundled. The fresh seven-point solve and generated source hash are
   retained; the different GUI fresh-run template is provided but was not
   separately executed during this preparation.

The core openEMS field-scan route currently reports `can_prepare=true` and
`can_run=false` on this machine. The separate EMerge extension did execute its
radiation case. An EMerge result must not be placed in the openEMS NF2FF result
slot or treated as proof that the core chamber scan ran.

## What the fields mean

This is a selected-net surface-PEC antenna fixture in a bounded absorbing air
domain with a supplied dielectric stack and port excitation. Full-fidelity
packages, losses, cables, receive antenna, chamber wall/absorber response and
receiver bandwidth/detectors are absent. Actual raw complex field samples are
retained, but the result contract only admits **relative normalization**. Do not
convert the plotted pattern into an absolute dBµV/m emissions claim.

Requested mesh is 2 mm; execution is not mesh/boundary convergence or measured
correlation. The screen's manually supplied dV/dt, dI/dt and loop area are
illustrative inputs. They are not extracted from this FEM result.

## Radiated immunity (RI)

Here RI means an externally applied RF field coupling into the board. This
requires an admitted incident-field source with direction/polarization and
field amplitude, board loads and induced terminal responses, plus any nonlinear
circuit/controller susceptibility criteria. The current SPIKE adapters do not
provide that workflow. A transmit pattern, S11, EMI risk score or visual receive
antenna is not an RI response.

`ri-scenario-not-executable.json` records an explicit future 1 V/m linear
coupling scenario, geometry identity, direction, polarization and requested
loaded-terminal response. It is a case specification, **not** a registered
solver request, and contains no synthetic response. It is not an IEC/MIL test
profile. RI remains blocked pending the incident-field/loaded-board contract,
physics implementation and validation; functional upset needs additional
device/firmware models and thresholds.

## Files, licenses and checks

Original board/scripts use SPIKE's Apache-2.0 notices; full LICENSE/NOTICE and
third-party notices accompany the pack. EMerge is separately installed under
its component-specific terms. No optional solver runtime is redistributed.
The documentation copied into EVIDENCE retains its existing individual notices.

`EVIDENCE/screening` contains the exact worker and native-save/readback records.
`radiation` contains the executed FEM result and host/frontend admission checks.
Static analysis images are renders of saved solver data, not UI screenshots.
No desktop recording was performed. The ZIP was read back and byte-hash checked.

From the repository: rerun `build.py`, the documented radiation runner, then
`package.py` in `examples/promo_showcase/em_chamber`. Existing numerical owners
are reused unchanged; no solver implementation or capability gate was modified.
