# Actual VESC4.12 Python-workspace analytics

The three `.py` files in this folder are ready to open in SPIKE's desktop Python workspace. They use `spike.analysis.run("validate_native_mna", ...)` and `spike.analysis.run("run_native_mna", ...)` and publish admitted plots/tables. They do not implement another solver. They are explicit reduced circuits tied to actual component values and net sets from the pinned BLDC_4 design; no whole-board extraction or ESC-control claim is made.

## Source and adaptation license

Board: Benjamin Vedder, **bldc-hardware / BLDC Driver rev 4.12**, [pinned source](https://github.com/vedderb/bldc-hardware/tree/f1c65014d0caab5d99d888fc3025377861ac6ae2), commit `f1c65014d0caab5d99d888fc3025377861ac6ae2`.

The original repository README licenses the VESC hardware under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). **Board-derived reference/value/connectivity evidence, reduced circuit netlists, native Studio project and board-derived figures/data in this analytics pack retain CC BY-SA 4.0**, with attribution to Benjamin Vedder and a statement of the adaptation. Adaptations select nominal capacitors, current-sense input RC components and phase dividers, omit the rest of the hardware, and add explicitly illustrative independent sources/source-loop assumptions. Retain this attribution, source link, license link and modification notice when sharing. Original SPIKE Python orchestration code uses Apache-2.0 as marked; that software notice does not relicense the derived hardware material. No endorsement is implied.

Source netlist SHA-256: `29430295c416ac7a69e0639ea5902b8b89d232b5bc3d2727f2b3dd58bf995f68`.

## GUI demo / recording sequence

1. Import the pinned `output/promo-esc-20261023/source/bldc-hardware-f1c65014d0caab5d99d888fc3025377861ac6ae2/design/BLDC_4.kicad_pcb` into SPIKE and select that board occurrence. Leave the board in view for an establishing shot.
2. Open **Python workspace**, choose **Open**, and select `examples/promo_showcase/esc/analytics/01_pi_supply_impedance.py`. Use the worker default Interpreter or a local Python with SPIKE's existing runtime dependencies. The templates fail if no board is selected, its name is not BLDC_4, or required component values/net sets differ from the pinned netlist.
3. Click **Run** (`Ctrl+Enter`), wait for **completed**, then **Show in viewport**. Show the source-component table, impedance plot and scenario-scope table. Narrate: "Actual nominal supply capacitors, with an explicitly supplied source loop; reduced linear network."
4. Repeat with `02_si_current_sense_filter.py`: show actual R50/R51/C36 evidence, gain and phase. Narrate: "The actual 100-ohm/100-ohm/2.2-nF differential current-sense input filter. Analog sensing SI, with an ideal unloaded amplifier input."
5. Repeat with `03_backemf_phase_divider.py`: show six actual resistor records and the divider sweep. The three curves coincide. Narrate: "The three actual 39k/2k2 phase-voltage dividers; the DC input sweep is supplied, not a motor simulation."
6. For a Studio waveform clip, open `examples/promo_showcase/esc/analytics/studio/vesc412_actual_phase_dividers.spksch` in SPIKES Studio. The project has 11 graphical wires and three saved scope probes. Run the transient and show the dashboard's three sense voltages. These are actual divider topology driven by supplied offset 100-Hz PWL phase sources, not actual motor back-EMF or closed-loop control. The accompanying `.cir` is editable source. Keep the scope/license note visible in the recording or caption.

The static PNGs in `output/promo-esc-20261023/analytics` are renders of actual published plot data, **not screenshots of the app**. Use the GUI sequence above to record the current app.

## What executes

- `01_pi_supply_impedance.py`: ten actual capacitors between V_SUPPLY/GND, 110 uF nominal total; a supplied 20 mOhm + 100 nH source-return loop and 1-A small-signal test current. Ideal C only: no ESR/ESL, bias derating, nonlinear inverter or trace extraction. AC response independently checked against the parallel C / series R-L closed form.
- `02_si_current_sense_filter.py`: actual R50=100R, R51=100R, C36=2.2n with 1-V differential small-signal excitation. First-order RC analytical check; corner about 361.7 kHz. No shunt resistance, DRV8302 gain/dynamics, ADC or EMI model.
- `03_backemf_phase_divider.py`: actual R23/R24, R26/R27 and R32/R33. Ideal DC divider sweep from 0 to 50 V; exact divider reference checked. No input loading, sampling/clamps, phase estimation, motor, switching bridge or controller.
- `studio/vesc412_actual_phase_dividers.spksch`: same actual divider topology, supplied 0–48 V offset sinusoidal samples at three phases; no ADC clamping/loading. It uses the existing packaged owned native transient engine. The three Python GUI templates use the existing registered linear-MNA worker operation, not a custom solver or an assertion of a specific C++ backend.

All results are experimental. The supplied scenarios are not component or system qualification, safety/rating approval, measured validation or completed ESC controls.

## Executed evidence and reproduction

Evidence directory: `output/promo-esc-20261023/analytics/`.

- `verification.json`: successful real child-process GUI execution of all three final templates against the actual imported board; final template SHA-256 hashes, solver counts and residuals.
- `*.script-request.json` / `*.script-result.json`: exact run_python_script requests and actual results, including selected design, stdout and admitted views.
- `*.worker-evidence.json`: exact registered worker requests and results, detached from stdout for inspection.
- `netlist-components.json`: actual parsed source references, values and pin/net membership.
- `studio/verification.json` / `studio/result.json`: native project reopen check, source-bound project hash, 2004 actual transient points and exact divider reference error.

From the repository root:

```powershell
.\.venv\Scripts\python.exe output\promo-esc-20261023\analytics\execute_verify.py
.\.venv\Scripts\python.exe output\promo-esc-20261023\analytics\render_views.py
.\.venv\Scripts\python.exe output\promo-esc-20261023\analytics\prepare_actual_studio.py
```

These commands expect the pinned downloaded source and `output/promo-esc-20261023/thermal/import-design.json` retained by the parent media pack. No network access is needed for the replay. `build_templates.py` reconstructs the templates from the retained netlist-component evidence; rerun `execute_verify.py` whenever templates change. It will retain new exact hashes. Studio generation records the native DLL hash separately. The templates check selected reference/value/net sets; this is useful design binding, not independent authentication of every CAD revision or a complete geometry-based extraction.
