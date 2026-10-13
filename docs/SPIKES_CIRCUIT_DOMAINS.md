<!-- SPDX-License-Identifier: Apache-2.0 -->
# Standalone circuit-domain examples

Six original netlists under `standalone/spikes_project/examples/domain-circuits`
provide bounded examples for circuit entry, execution, and CSV waveform plotting.
They run directly in **ngspice**; they are not evidence that SPIKES owns a native
solver for these domains. Run a deck in a writable directory with:

```text
ngspice_con.exe -b example.cir
```

Each deck writes a named, whitespace-delimited CSV file whose first row contains
vector names. Time is seconds, frequency is hertz, voltage is volts, current is
amperes, resistance is ohms, inductance is henries, and capacitance is farads.
The numerical regression test copies decks to a temporary directory, bounds each
external process to 20 seconds, and skips execution if ngspice is unavailable.

| Deck | Analysis | Plot columns | Analytical check |
| --- | --- | --- | --- |
| `rf_series_resonance.cir` | AC | frequency, resistor-voltage magnitude | Series LC resonance near 31.62 MHz and unity resistor voltage |
| `highspeed_matched_interconnect.cir` | transient | time, near/far voltage | 5 ns ideal propagation delay and 0.5 V matched amplitude |
| `precision_bridge_ideal_amplifier.cir` | operating point | bridge nodes, output | Resistor-divider result and explicitly ideal VCVS gain |
| `pwm_buck_ideal_switch.cir` | transient | time, output voltage, inductor current | Settled mean near duty ratio times input |
| `hv_rc_divider.cir` | transient | time, sense voltage | 10:1 final ratio and 9 ms first-order time constant |
| `low_voltage_high_current_path.cir` | transient | time, load voltage, path current | 100 A DC limit from the declared 0.12 ohm path |

These are analytical education and integration fixtures, not product models.
The transmission line is ideal and lossless. The bridge amplifier is an ideal
dependent source, not a vendor op-amp and not an error/noise/stability model.
The PWM buck uses idealized switch and diode models and establishes neither
converter stability nor semiconductor, magnetic, EMI, efficiency, or thermal
qualification. The 1000 V deck omits creepage, clearance, insulation, probe,
arc, surge, and personnel-safety behavior. The 100 A deck omits temperature,
current sharing, magnetic saturation, source limits, fusing, and interconnect
geometry. No fixture establishes PCB signal integrity, RF/full-wave behavior,
precision-instrument performance, compliance, or hardware safety.

The executable acceptance evidence is
`standalone/spikes_project/tests/python/test_domain_circuits.py`. It validates
only the equations and tolerances named above against the actual external
ngspice result; it contains no synthetic or fabricated waveform fallback.
