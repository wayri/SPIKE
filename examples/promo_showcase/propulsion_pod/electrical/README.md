# Restrained propulsion-pod electrical starter

Two editable native SPIKE Studio projects exercise a **supplied bus/load transient** and an **ideal shunt-sensing chain**. These are firstparty, Apache-2.0 examples. They are intentionally bounded electrical teaching models, not a complete ESC, motor, propeller or drone simulation. No third-party code, compact model, firmware or native DLL is bundled.

## Open in Studio

1. Use **File > Open `pod_bus_startup.spksch`** so its actual graphical wiring, probes and three scope widgets are retained. Run the native transient; inspect V(supply), V(bus), I(Iload). Dashboard Run mode displays real recorded samples. The saved profile selects backward Euler, 1 µs, 4 ms.
2. Open `current_sensing.spksch`, run its native transient, and inspect V(shunt), V(adc), I(Rshunt) through the saved scopes/probes.
3. Select the current main native engine at `app/src-tauri/resources/worker/spike-worker/_internal/spikes/spikes_c_api.dll` when Studio requests it. Its path/hash is in the verification output. The inspected sibling circuit-worker DLL lacks the dependent-source ABI required by the ideal sense amplifier. No installed-runtime compatibility beyond that recorded DLL is implied.

Plain matching `.cir` inputs are also included. The `.spksch` files were actually loaded/validated through the existing native Studio Document API; no interactive UI session or recording was performed.

## Inputs and executed checks

`pod_bus_startup`: a prescribed voltage ramps 0→48 V over 200 µs, through assumed 0.1 Ω source resistance and 1 µH lead inductance. Bus capacitance is an assumed 470 µF with 20 mΩ ESR. The ideal current load ramps to 0.2 A, steps to 5 A around 1 ms, then returns to 0.2 A around 2 ms. This is a test stimulus, not demand extracted from the physical pod or a rotating motor.

| Actual native run | Light load bus | 5 A load bus | Recovered bus |
| --- | --- | --- | --- |
| 1 µs, 4001 samples | 47.979948 V | 47.500000 V | 47.980000 V |
| 0.5 µs, 8001 samples | 47.979952 V | 47.500000 V | 47.980000 V |

At steady state the lead inductance has zero voltage and the capacitor carries zero DC current, so independently `Vbus=48−0.1 Iload`: 47.98 V and 47.50 V. Both native runs match the reference within the unchanged 5 mV acceptance. Step halving changes the settled droop by approximately 4.1 µV, below the unchanged 1 mV refinement criterion. This is a bounded circuit check, not a general stability, hardware inrush or power-distribution qualification.

`current_sensing` is copied unchanged from the firstparty ESC starter. A prescribed 20 A pulse passes through 1 mΩ; the ideal voltage-controlled gain is 50 followed by a 1 kΩ/1 nF filter. Executed 3001-sample result gives 20 mV shunt peak and 1.000 V ideal amplified peak. There is no ADC quantization, noise, rail limitation, amplifier bandwidth model or sourced shunt rating.

## Reproduce

From the repository root:

```powershell
.venv/Scripts/python.exe examples/promo_showcase/propulsion_pod/electrical/run_examples.py
```

This uses existing owned native C++ circuit execution, prepares only this subfolder's bus Studio document, and writes raw executed results plus verification under `output/promo-propulsion-pod-20261023/electrical/`. It does not implement or change any solver. Native library and source hashes are retained in verification/provenance.

## Motor/controller scope audit

Existing support was inspected in `examples/spikes/advanced_systems/README.md`, `docs/EM_MACHINES.md`, the native Studio run-control API and the actual current native DLL. SPIKE has a separate sampled C controller with an averaged PMDC armature/mechanical state, and separate prescribed-current planar machine FEM. Those do not establish a native three-phase sensorless ESC, field-coupled controller, propeller load or thrust-driven pod demand. The automotive two-wheeler dashboard and its hypothetical 72 V mapping are therefore not relabeled as a pod motor here.

The next meaningful extension needs explicit motor/drive/propeller data and appropriate validated model contracts. This starter does not couple its load pulses to the separate mechanical, thermal, CFD or KiCad geometry work; battery chemistry/SOC, switching losses, rotor fields, airflow, thrust and thermal feedback remain absent. Hardware ratings, wire/connector sizing and safe operation require their own evidence.
