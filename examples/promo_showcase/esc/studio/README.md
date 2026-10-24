# ESC-related native SPIKE Studio projects

These four ready native projects demonstrate actual supported Studio circuit execution. They are original illustrative SPIKE examples, not a VESC4.12 circuit/firmware reproduction. Apache-2.0; LICENSE and NOTICE included. Their raw results are in `output/promo-esc-20261023/studio/`.

## Open and demonstrate

Use **File > Open** on `.spksch` to retain graphical wiring, saved probes, scopes and dashboard. Batch transient projects have three configured scope widgets; run the native simulation, select Dashboard Run mode and inspect recorded samples. In schematic/plots inspect saved probes, cursors and actual circuit source.

| Project | Actual model and useful inspection | Fresh checks |
| --- | --- | --- |
| `backemf_sensing.spksch` | Supplied 24 V peak 100 Hz phase waveform sampled as explicit 100 us PWL points; 200k/10k divider, ideal unity buffer with supplied 1.65 V offset, 1k/100n filter. Scopes: phase, divider, ADC. 10 real source-bound wires. | 4004 samples; divider max error 1.11e-15 V; settled ADC 0.510–2.790 V. |
| `current_sensing.spksch` | Supplied 20 A current pulses into 1 mΩ shunt, ideal gain 50 and 1k/1n filter. Scopes: shunt voltage, ADC, shunt current. 8 real wires. | 3001 samples; peak shunt 20 mV, ADC 1 V. |
| `gate_miller_ringing.spksch` | Supplied gate/drain edges, gate-loop L/R and fixed Cgs/Cgd. Scopes gate, drain, package current. 9 real wires. | 3000 samples; gate peak 15.697 V, minimum -3.692 V. |
| `two_wheeler_dashboard.spksch` | Native armature R/L plus embedded C PI controller and sampled mechanical/back-EMF state. Controller: review source, trust/compile, attach to Continuous, run closed loop. Dashboard Run mode, Throttle 0.2 Send, then Brake; normal pause/resume/stop. Source also included as matching `.c` and `.cir`. | Fresh exact copied project run: 30% throttle gives positive native current/speed; full braking gives negative current. |

For native engine selection, use the Studio action that opens **Select SPIKES native engine**, selecting `app/src-tauri/resources/worker/spike-worker/_internal/spikes/spikes_c_api.dll` from this repository. Its actual SHA-256 is in verification.json. The sibling **spike-circuit-worker** DLL lacks dependent-source ABI in the inspected current installation and cannot run the two ideal amplifier examples. No native DLL is redistributed here. Studio desktop CLI also supports `--library <path>`.

## Scope of the result

Back-EMF excitation is supplied analytically and retained as explicit piecewise-linear samples; no rotating motor fields or phase commutation generate it. Ideal amplifiers have no rail limits, bandwidth/noise/offset or ADC loading/quantization. Sensor component choices are illustrative, not VESC board matches or hardware front-end recommendations. Gate-loop result is linear capacitive injection, not a nonlinear Miller plateau, switching-loss prediction, avalanche/recovery or manufacturer MOSFET qualification.

The controller example is an averaged PMDC equivalent, not three-phase PWM/FOC, sensorless BLDC commutation, VESC firmware or controller-driven FEM. Its temperature/bus channels are controller estimates, not semiconductor thermal/PI solves. Use the separately supplied ESC board PI/SI/thermal projects for their own documented scope; there is no automatic coupling to these sensor or controller decks.

No UI recording was performed. Schematics were generated with the existing `Document.from_netlist`, source-authoritative `connect`, saved-probe and dashboard APIs, saved as actual native projects and reopened/validated. Results came from the owned native C++ engine and the actual trusted example controller; no solver was added or modified. The graphical routes join original identical nets and do not imply physical board routing.

## Rebuild and verify

From repository root:

```powershell
.venv/Scripts/python.exe examples/promo_showcase/esc/studio/prepare_verify.py
```

This rewrites only the prepared Studio examples and their dedicated output results. It compiles the trusted original C controller in a repository-local temporary directory. A working supported C compiler is required. Do not connect this educational example to hardware.
