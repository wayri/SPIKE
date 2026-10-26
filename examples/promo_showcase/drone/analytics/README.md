# IRIS board-derived analytics for the SPIKE GUI

Two executable Python-workspace scripts use actual pinned IRIS board connectivity and BOM nominal values. They call registered `validate_native_mna` and `run_native_mna` operations through `spike.analysis.run`; no new solver or physics implementation is introduced.

Source: [Eugene109/IRIS](https://github.com/Eugene109/IRIS/tree/999dd2eb725d550889c1ffe2c09f8de0390d081b), commit `999dd2eb725d550889c1ffe2c09f8de0390d081b`. The PCB was converted upstream from EasyEDA and all 244 imported component Value fields are blank. The scripts retain that fact: they verify selected imported component references/net sets and join nominal values from the separately pinned `pcb/fabrication/BOM.md`. This is source-derived reduced circuit analysis, not a general CAD-to-physics extraction or complete design validation. Upstream conversion/import warnings remain open.

## Scope

- `01_pi_battery_bus.py`: 17 actual capacitors connected directly between `7.4V_BATTERY` and GND, nominal total **1594 uF** from the BOM. A **supplied 30 mOhm + 150 nH** source-return loop and 1-A AC stimulus produce the driving-point impedance. Those R/L values are illustrative assumptions, not extracted board, cable, package or battery properties. Ideal capacitance only: no ESR/ESL, DC bias derating, switching inverter or battery chemistry.
- `02_si_i2c_pullup.py`: actual **R11/R12=2.2k**, on I2C1 SDA/SCLK, with **supplied 50/100/200 pF** bus capacitance sensitivity. An ideal source step gives a release-equivalent first-order charging scenario. No actual open-drain device, IO nonlinearities, sensor/MCU dynamics, thresholds, clock stretching, protocol/firmware, crosstalk or geometry-based SI is simulated. The RC rise-time values are not I2C compliance claims.
- `studio/iris_actual_i2c_pullups.spksch` and editable `.cir`: same actual pullups with supplied 100-pF loads and ideal PWL source, two saved scope probes and six graphical wires. This uses the existing packaged owned native transient engine. It is a reduced circuit demo, not a complete flight controller or drone simulation.

All cases remain experimental. These results do not establish whole-flight control, propeller CFD, motor/ESC switching validity, manufactured-board performance or safety qualification.

## GUI recording sequence

1. Import and select `output/promo-drone-20261023/source/ProPrj_IRIS.kicad_pcb`. Start with the actual board view and retain conversion warnings in the accompanying explanation.
2. Open **Python workspace** → **Open** → `examples/promo_showcase/drone/analytics/01_pi_battery_bus.py`. Leave Interpreter at worker default or select a Python installation with the existing SPIKE dependencies. Click **Run** (`Ctrl+Enter`), wait for **completed**, then **Show in viewport**. Show actual component table, impedance plot and scope table. Caption: "Actual IRIS battery-net capacitor membership and BOM values; supplied source-loop scenario."
3. Repeat with `02_si_i2c_pullup.py`. Show the actual R11/R12 evidence, three capacitance-sensitivity curves and analytical table. Caption: "Actual IRIS I2C pullups; explicitly assumed bus capacitance and ideal charging stimulus."
4. In SPIKES Studio, open `examples/promo_showcase/drone/analytics/studio/iris_actual_i2c_pullups.spksch`, run, and show the two scope widgets. Narrate the supplied step/capacitance assumptions. Keep the source/license/scope note in frame or in the post caption.

Templates fail when the selected board name is not `ProPrj_IRIS` or selected component connectivity/blank-value state differs from the retained source. They do not independently authenticate every CAD revision. The PNGs in the output analytics folder are renders of actual published plot data, **not app screenshots**.

## Executed checks and retained evidence

All final templates executed through real `run_python_script` child processes, bound to `output/promo-drone-20261023/thermal/import-design.json`. Four existing worker solves completed, publishing seven admitted views.

- PI maximum complex closed-form comparison error: `2.06e-16 ohm`.
- Pullup transient maximum error against exponential RC reference: `0.02973 V` on a 3.3-V step, below the fixed `0.035 V` check. The 1-ns fixed-step backward-Euler grid resolves the fastest 110-ns RC case. The edge-inclusive step implementation contributes the maximum one-step difference; no physical accuracy claim is inferred.
- Native Studio: reopened project, 4001 actual samples, identical SDA/SCLK responses, maximum RC comparison error `0.00745 V` (check bound 0.02 V).
- Final template SHA-256 and native project/DLL hashes are retained in verification records. Static plots were visually inspected for titles, units, legends and qualification footer.

`output/promo-drone-20261023/analytics/` contains `source-evidence.json`, parsed PCB evidence, full GUI requests/results, exact worker requests/results, per-case full `*.actual-result.json`, verification and static PNGs. The evidence harness sets `SPIKE_ANALYTICS_EVIDENCE_DIR` so full results are written locally without overflowing bounded GUI stdout; ordinary GUI runs publish plots/tables and concise diagnostics.

From the repository root, after the parent source/import preparation:

```powershell
.\.venv\Scripts\python.exe output\promo-drone-20261023\analytics\execute_verify.py
.\.venv\Scripts\python.exe output\promo-drone-20261023\analytics\render_views.py
.\.venv\Scripts\python.exe output\promo-drone-20261023\analytics\prepare_actual_studio.py
```

No network access is required for replay. `build_templates.py` rebuilds templates from exact parsed PCB/pinned BOM evidence; rerun execution verification after changing them.

## Attribution and redistribution

IRIS source project attribution: **Eugene109 / IRIS**. The upstream root license is GNU GPL version 3; a copy is retained as `LICENSE`. This analytics directory's board-derived source/evidence, reduced circuits, native project and figures are distributed under **GPL-3.0-only**, preserving the upstream license, attribution and editable corresponding sources. Adaptations: source reference/connectivity-to-BOM join, reduced passive networks, supplied stimuli/source-loop assumptions, and SPIKE API/report orchestration. Retain these notices and matching editable source/evidence when sharing derived artifacts. No author endorsement is implied. This analytics scope includes no third-party assembly/propeller model.
