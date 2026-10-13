# ADR 0063: Compiled internal-engine board objects

Status: Accepted for bounded engineering-preview source implementation; general
board fidelity, firmware emulator integration and release qualification pending.

## Context

Software needs an instantiable electrical peripheral whose state persists across
drive/advance/read operations. Batch waveform files do not provide that boundary.
Existing internal SPIKES transient sessions already own circuit state and native
checkpoints. The export must preserve their numerical contracts and avoid
claiming physics absent from the supplied netlist.

## Decision

Python validates a bounded circuit and declared pins, generates original C++ data
definitions and compiles a board-specific shared library against the existing
owned SPIKES C ABI. The package includes a C API, a C++ RAII object header,
normalized circuit data and a versioned manifest with artifact/engine hashes.
Python loading explicitly verifies the package and selected engine before native
loading. Hashes provide reproducibility and change detection, not publisher
authentication or a sandbox for native code.

Each board instance owns its own native circuit/session. Inputs are voltages
applied through finite declared resistance, with finite bounds; values are held
between drive operations. Outputs are declared node voltages or branch currents.
Time is simulated seconds, and steps obey explicit size/count/horizon limits.
Save/restore/reset are object-local. Failed advancement must restore its prior
state; invalid input must be rejected without mutation. Calls to one object must
be serialized by its owner.

The initial compiler admits only RLC and constant independent sources. Broader
kernel capabilities do not implicitly become exporter capabilities. Unsupported
models fail explicitly. A host-compiled firmware example exercises ADC sampling
and threshold polling over a resistively loaded RC circuit. This is not MCU
instruction emulation, an FMU or a universal board model.

## Consequences and evidence

The native solver remains the numerical authority; Python owns contracts and
compilation, and no alternate solver is embedded in the wrapper. Acceptance
requires an actual compiled library, a linked C++ client, analytical circuit
comparison with stated tolerance, timestep refinement, independent objects,
state replay, and rejected invalid input/artifact changes. Numerical human review
before release remains required by `CONTRIBUTING.md`.

FMI, SystemC/Renode and external SPICE engines are future adapters. Their time,
protocol, restart, licensing and accuracy requirements must be established
independently. See [research and extension order](../BOARD_LIBRARY_RESEARCH.md)
and [the implemented package contract](../COMPILED_BOARD_LIBRARY.md).
