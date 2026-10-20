<!-- SPDX-License-Identifier: Apache-2.0 -->
# Finite edge and power-integrity teaching examples

Open these decks in Studio with the explicitly selected owned C++ backend.
All parameters are synthetic assumptions, not characterized manufacturer pads.

- `rlc_edge_ringing.cir`: plot `v(bus)` and `i(L1)`. An ideal-step reference has
  alpha=1e8/s and damped frequency3e8rad/s; the actual source has a finite1ps
  rise. Refine the electrical step rather than equating firmware time resolution
  with waveform accuracy.
- `pdn_load_step.cir`: plot `v(rail)` and `i(RS)`. The20mA increment has final
  resistive droop10mV and nominal relaxation time0.5us. The source has1ns edges.
- `open_drain_release.cir`: a finite30ohm sink releases a2.2kohm/100pF bus.
  Plot `v(bus)`; release cannot create an instantaneous logic-high.

These static circuits do not execute SPI/I2C firmware. The source SDK's
`standalone/spikes_project/tests/python/test_firmware_bus_examples.py` is the
executable synthetic bidirectional SPI/I2C harness: finite target pads implement
ACK/NACK and stretching, and receiver decisions use actual C++ node voltages.
It also checks closed-form RC/RLC/PDN references and contention. MCU GPIO
instruction coupling is a separate explicitly trusted workflow documented in
Studio help, `GPIO_PIN_WORKFLOW.md`; peripheral PWM/SPI/I2C routing is not
qualified by these circuits.
