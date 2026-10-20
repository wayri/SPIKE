<!-- SPDX-License-Identifier: Apache-2.0 -->
# Synthetic finite-pad SPI/I2C and SI/PI teaching fixtures

These executable examples are original Python test controllers driving the
owned native C++ electrical solver. They are **not** MCU binaries, Renode
peripheral emulation, or qualified physical SI/PI predictions.

Run from the repository root with a built native library:

```powershell
$env:SPIKES_TEST_NATIVE_LIBRARY = (Resolve-Path build-spikes-io-pad-20261019/Release/spikes_c_api.dll).Path
python -m unittest discover -s standalone/spikes_project/tests/python -p test_firmware_bus_examples.py -v
```

The source fixture is
`standalone/spikes_project/tests/python/test_firmware_bus_examples.py`.
It constructs circuits directly so finite GPIO mode changes, sampling and
feedback remain executable; a static SPICE deck cannot express this controller
contract.

- SPI mode-zero synthetic electrical loopback sends 0xA5 through finite MOSI
  and MISO pads, with actual voltage-derived reads and CS framing. Increasing
  MISO capacitance from 20 pF to 1 uF must corrupt the received byte.
- I2C sends an original 0xA5 byte through two open-drain participants with
  2.2 kohm pull-ups and 100 pF wire capacitance. It checks ACK and NACK, a
  deliberate 2 us clock stretch, physical SCL recovery delay, START and STOP.
  ACK and stretching use finite target pad sinks, never out-of-band Boolean
  injections into the receiver.
- RC release compares the continuous exponential with sampled receiver
  observations on three grids; the observed crossing is delayed by at most one
  sample. This fixture does not implement a continuous root localizer.
- A 20 ohm / 100 nH / 100 pF series network verifies ringing, inductor current,
  first-peak time, grid refinement and source/loss/storage energy balance.
- A 0.5 ohm / 1 uF PDN with a 20 mA load increment verifies the exact rail
  droop and branch currents, and separately checks the no-decoupling limit.
- Two finite push-pull outputs verify 33 mA contention, 1.98 V bus voltage and
  dissipation without last-writer-wins digital resolution.

Analytical method, predeclared tolerances, source review and qualification gaps:
[independent evidence contract](../../../../docs/validation/BIDIRECTIONAL_GPIO_BUS_20261020.md).
All component values are synthetic assumptions, not manufacturer parameters.
Only the exact tests executed successfully may be claimed as software
verification; these examples establish no hardware peripheral timing,
metastability model, board extraction, distributed interconnect accuracy,
whole-standard compliance, or silicon validation.
