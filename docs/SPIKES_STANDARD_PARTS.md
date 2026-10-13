<!-- SPDX-License-Identifier: Apache-2.0 -->
# Standard parts library increment (2026-10-12)

The Studio manufacturer browser and quick canvas search now include 33 additional
package-specific records: 20 TI HC logic packages and 13 analog/discrete parts.
Existing sourced records remain intact. Custom catalog paths are loaded unchanged;
only the bundled default catalog receives the extension.

## Executable functional logic

`python/spikes/standard_logic.py` owns independently authored Boolean package
descriptors for SN54HC00J/02J/04J/08J/10J/11J/20J/21J/32J/86J and
SN74HC00N/02N/04N/08N/10N/11N/20N/21N/32N/86N. Each exposes all fourteen package pins, including
VCC and GND. NOR, inverter, triple-three-input and dual-four-input layouts are
distinct. HC20/21 pins 3 and 11 are explicitly unconnected.

`package(part)` returns a fresh descriptor. `bind(kernel, part, instance,
mapping, delay_ticks=...)` binds each gate to the existing four-state DigitalKernel.
Mapping keys are physical pin-number strings; every target signal must already
exist. Failed preflight does not partially install a package. Delay is explicitly
supplied in caller-defined ticks and uses existing transport semantics. Power
pins are declared only: no supply-dependent behavior or circuit coupling exists.

`spice_recipe(part, output_resistance_ohm=..., input_capacitance_f=...,
transition_v=...)` produces a separate **unqualified generic electrical** subcircuit
for an explicitly selected ngspice-compatible backend. It has a smooth tanh
half-supply transfer, user-selected Rout and Cin, and no delay. This is not
manufacturer SPICE, an IBIS substitute, or an SI-qualified pad model. Parameters
have SI units and must be finite/positive. No default electrical parameters are
claimed for named products. Native Studio placement remains disabled until the
circuit/backend integration is reviewed.

Pin/function facts come from TI's official datasheets, accessed 2026-10-12:
[HC00](https://www.ti.com/lit/ds/symlink/sn74hc00.pdf),
[HC02](https://www.ti.com/lit/ds/symlink/sn74hc02.pdf),
[HC04](https://www.ti.com/lit/ds/symlink/sn74hc04.pdf),
[HC08](https://www.ti.com/lit/ds/symlink/sn74hc08.pdf),
[HC10](https://www.ti.com/lit/ds/symlink/sn74hc10.pdf),
[HC11](https://www.ti.com/lit/ds/symlink/sn74hc11.pdf),
[HC20](https://www.ti.com/lit/ds/symlink/sn74hc20.pdf),
[HC21](https://www.ti.com/lit/ds/symlink/sn74hc21.pdf),
[HC32](https://www.ti.com/lit/ds/symlink/sn74hc32.pdf),
[HC86](https://www.ti.com/lit/ds/symlink/sn74hc86.pdf).
Only factual pin/function metadata is transcribed; no vendor model, code or
datasheet artwork is redistributed. Original model code is Apache-2.0.

## Analog discovery, not invented precision

New records: TL072CP, NE5532P, OPA197IDR, INA128P, AD620ANZ, AD623ANZ,
2N3904BU, 2N3906BU, MMBT2222ALT1G, FQP30N06L, BC847B,215,
BC857B,215, and 2N7002,215. Each carries manufacturer URL, access date,
package pin inventory and sourced rating metadata. These are review-only;
no executable analog model or manufacturer qualification was added. Existing
LM358/LM741 records remain available. The browser's disabled insertion state is
intentional, not evidence that a generic opamp accurately represents the MPN.

## Verification and remaining work

Tests enumerate every supported package/gate truth table, unknown propagation,
user-defined delay, pin layouts, errors and caller-mutation isolation. The
electrical test runs 140 ngspice DC cases and checks loaded output levels; this
validates the original generic recipe only, not vendor switching performance.

Full 54/74 coverage, LS/HCT/AHC/LVC and other families, sequential logic,
electrical mixed-signal binding, qualified analog/vendor models and SI timing
remain pending. MCU binary execution is separate and remains unavailable; see
[firmware admission](SPIKES_FIRMWARE_EMULATION.md). Wall-clock speed does not
establish peripheral-cycle or electrical timing accuracy. Numerical/electrical
models still need knowledgeable human review before release.
