# Owned electrical GPIO pads

SPIKES now has an experimental C++ electrical GPIO layer independent of the
instruction emulator. Renode remains the explicitly selected CPU/peripheral
backend; it does not solve the pin network. The previous DI/DO ideal-voltage
bridge remains a separate mode and is not silently upgraded or substituted.

## Electrical network

Each pad connects to an external signal net and actual circuit VDD/VSS nets.
The owned MNA engine solves finite high/low output resistances, high-impedance
leakage, independent internal pull resistances, optional package R/L, separate
die capacitance to each rail, and optional generic rail-clamp diodes. It handles
push-pull, open-drain, open-source and input/released modes. Shared open-drain
buses resolve electrically; competing push-pull drivers produce finite current.

Native branch currents/power and three terminal currents include charge flow.
Current is positive **entering** the pad network at each terminal. Supply and
ground are not forced ideal: external PDN impedance can produce droop/bounce.
This is a lumped model, not distributed transmission-line or field extraction.

## Profiles and firmware coupling

`python.spikes.native_io_pad` exposes immutable `PadProfile` / `PadState`,
`add_pad`, `set_pad`, `observe_pad` and `receive`. These functions call the owned
C ABI. There is no Python pad solver. Native sessions copy pad configuration,
and native checkpoints restore the pad-state cache as well as circuit history.
Individual generated pad branches cannot be modified with the ordinary C ABI
resistor setter; use `set_pad` to keep their states coherent.

`spikes_studio.firmware_electrical.ElectricalFirmwareController` accepts explicit
`PadConnection` entries: GPIO port/pin, signal net, supply net, return net,
profile and input thresholds. Pass it as `controller=` to `InteractiveRun`, or
use `bind` / `configure_circuit` / `advance` with a native session. All terminals
must be existing project nets. There is no implicit conversion of the old
DI/DO source bindings. The firmware manager also exposes this through **Circuit coupling** and
**Electrical pin properties**. Legacy ideal DI/DO remains an explicit separate
choice. See [GUI pin and timestamp workflow](GPIO_PIN_WORKFLOW.md).

STM32F407 and nRF52840 register decoders select output type, level, input-buffer
state and internal pulls. Nordic mixed-strength settings select the explicit
profile's applicable active-side resistance. STM32 speed-register settings are
retained as categories, not turned into invented edge rates. Reserved states,
STM32 analog/alternate functions and unimplemented pins fail explicitly.

Profiles' defaults are illustrative generic values, **not manufacturer models**.
Users must provide characterized R/C/L, clamp data and thresholds for a physical
device. No vendor IBIS file import or IBIS compliance is claimed.

## Execution and limits

Run `examples/spikes/controller_firmware/native_pad_echo.py --help` from the
source checkout for an original binary-to-electrical-plant example and optional
CSV export. Execution requires explicit `--approve-firmware`; review the image
and runtime first. This invokes a separately installed approved Renode runtime.

Coupling is endpoint-sampled: at plant boundary `t`, the backend catches up
from `t-delta` using the sampled input, then its configuration is applied to the
next plant interval. It is **not event-synchronous causal timing**. Intra-tick
pulses, pad-mux peripheral activity, SPI edge timing, metastability, ADC/DAC,
MCU power consumption/brownout and full ESD/damage behavior are not modeled.
The explicit generic Schmitt receiver retains known state only inside its
threshold band. Disconnected history is cleared; unresolved input or nonpositive
rail span stops rather than inventing a Boolean level. Positive rail span does
not by itself establish a valid MCU operating supply.

Pause retains the real native plant and emulator state. A native electrical
checkpoint alone is not a firmware checkpoint: one-sided restore/repeated
firmware ticks are rejected by clock alignment. Failed electrical steps stop
the coupled run; there is no combined rollback or hard-real-time guarantee.

The foundation permits later SPIKE SI/PI network attachment. Captured software
GPIO timestamps are available through the separate explicit mode below;
peripheral ownership, nonlinear characterized buffers, vendor model evidence,
temperature dependence and measured board comparisons remain necessary for
qualified high-speed SI/PI use. Human numerical/device review remains required
before release. See `docs/validation/NATIVE_GPIO_PAD_20261019.md` in the main
repository for independent equations and executed verification scope.

## Timestamped software GPIO

The GUI's timestamped mode captures actual CPU GPIO register changes using the
approved runtime's public bus hooks and synchronized virtual clock. It uses
single-instruction translation blocks: this avoids block-start timestamp
quantization but is substantially slower. Time values are virtual integer
nanoseconds, not host timestamps or a cycle-accurate hardware claim.

Native C++ queueing integrates to each captured edge before changing pad mode,
preserving storage state. Stable ordering, bounded capacity and checkpointed
queue/mode restoration prevent dropped or reordered transitions. Endpoint
observations are left-limit samples; the new mode governs the next interval.
Continuous acquisition retains accepted edge-time points and reporting-grid
points inside its existing bounded ring. Select an adequately small reporting
step to resolve ringing between edges; capturing edge times does not guarantee
all intermediate extrema are sampled.

This is bounded lookahead with inputs held at each interval's start, **not
continuously synchronized input feedback**. Capture admits at most 32 pins,
256 changed records and 1 ms per firmware interval. DMA, autonomous PWM,
alternate functions, GPIOTE/PPI and reset during capture are unsupported;
detected unsupported activity or overflow rejects the batch. Initial alternate
function pins (for example STM32 debug pins) fail rather than becoming invented
high-Z GPIOs. Startup requires a converged operating point, no UIC; time-zero
mode changes before OP/storage acceptance are rejected. Generic profiles remain
unqualified, and physical SI/PI validation remains outstanding.
