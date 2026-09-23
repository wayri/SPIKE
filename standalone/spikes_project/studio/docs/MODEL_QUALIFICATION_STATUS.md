# Model qualification status — source audit, 7 September 2026

Qualification is specific to a model implementation, backend, analysis, parameter
range and evidence dataset. An illustrated symbol or a parsed .MODEL card is not
evidence that the device is executable. A static reference evaluator is not a native
transient model. No family-wide manufacturer accuracy claim is made here.

| Family | Native standalone execution | Preview | Evidence boundary |
|---|---|---|---|
| R, L, C | Linear models | Topology and analytical impedance | Analytical/native circuit tests, not material characterization |
| Capacitor package | Explicit ESR/ESL/leakage network | Topology and impedance | DC leakage and ESR transient time-constant checks |
| Voltage/current source | DC, PULSE, PWL | Source symbol and declared waveform | Ideal source; no compliance or output-stage parasitics |
| Diode | Static Shockley junction | Diode symbol and bounded I–V | Four native DC points against equation; no recovery/capacitance/breakdown qualification |
| Smooth switch | Native tanh conductance | Control terminals and R–Vcontrol | Three native DC points against equation; not a hysteretic switch or transistor |
| NPN BJT / NMOS level 1 | Native DC and BE/BDF2 transient with explicit charge parameters | Unavailable | Equation, charge conservation and circuit tests; not manufacturer qualification; trapezoidal transient remains rejected |
| BSIM-BULK / BSIM-CMG | Pinned Berkeley OSDI modules, Windows DC/BE transient | Unavailable | Full circuit execution tests; isothermal four-terminal cards, not foundry qualification |
| JFET / IGBT / thyristor | No production compact-model binding | Unavailable | Generic IGBT/SCR behavioral subcircuits now supplied; limited dynamic tests, not vendor accuracy |
| GaN / SiC | Native SPK_GAN / SPK_SIC electrothermal extensions | Unavailable | Generic turn-on and thermal tests, not vendor model compatibility or qualification |
| Behavioral B sources | Native nonlinear DC and transient, bounded expression graph with analytic derivatives | No universal preview | Nonlinear feedback, conditional, table and time-expression tests; not complete vendor expression dialects |
| IC/ADC/DAC/op-amp/RF/macromodel | Depends on complete subcircuit primitive support | No universal detailed preview | Every primitive and analysis must be executable; parsing is insufficient |
| Magnetic/mechanical/electrothermal | No universal native model family | No universal detailed preview | Reduced examples and explicit networks are not vendor qualification |

Source audit: `python/spikes/native_runner.py::_populate` defines the current owned
runner boundary. It does not automatically register all model classes in
`static_compact_devices.py`, `dynamic_devices.py`, or `osdi_runtime.py`.

Preview curves use the actual parsed parameters. The diode range spans -5 to 20
thermal voltages; this display range avoids huge exponentials but is not a physical
validity envelope. Source time axes show the declared waveform, not acquired solver
samples. The switch curve uses the same tanh conductance law as the owned C++ model.

## Requirements before enabling a validated detailed model

1. Record exact model files, version/hash, source, license and redistribution rights.
2. Bind every terminal, internal state, residual/Jacobian and charge/flux contribution.
3. Declare supported analyses and operating envelopes, including temperature.
4. Compare DC, AC, transient and relevant noise behavior to manufacturer data or
   measurements with explicit tolerances. Retain raw evidence and test scripts.
5. Exercise convergence, timestep rejection, initial conditions, reverse operation,
   breakdown and parasitic behavior where applicable.
6. Record engine/compiler/platform hashes and isolate unsupported operating regions.

These gates are not yet met for detailed manufacturer device families. Keep their
validated tier disabled. Passing generic equation tests must never unlock that tier.
