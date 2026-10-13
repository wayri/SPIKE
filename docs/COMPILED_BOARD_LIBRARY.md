# Compiled board objects

SPIKES can compile a normalized circuit snapshot into a board-specific shared
library. A host C/C++ program or Python client creates independent board objects,
drives declared analog pins, advances simulation time, and reads solved voltages
and currents. The board library links to the separately installed owned SPIKES
engine through its persistent C ABI. External engines are not supported by this
exporter. See [the co-simulation research](BOARD_LIBRARY_RESEARCH.md) for broader scope.

The bounded export supports lumped resistors, capacitors, inductors, constant
independent voltage/current sources, the static Shockley diode, and static NMOS
Level-1 without charge parameters. The diode and NMOS parameter lowering is the
same explicit mapping used by the owned native runner. Other devices, source
waveforms, behavioral sources, AC phasors, sweeps, measurements, nondefault
circuit temperature, and NMOS charge terms are rejected. Flattened hierarchy
and element initial conditions are retained.
The explicit board limits replace analysis timing; the original analysis remains
in `circuit.json` as provenance, and is not an additional executed analysis.

## Build and use

Use Python 3.11+ and the same architecture as the installed native engine. On
Windows, run from an x64 Visual Studio C++ developer command prompt so `cl.exe`,
`INCLUDE`, `LIB`, and runtime DLL directories are configured. The export uses
C++20 and requires the engine's matching import library. On Linux the compiler
defaults to `c++`; use `--compiler` to select an exact executable. Windows x64 is
the integration-tested platform for this change; Linux/macOS compilation paths
are implemented but have not been exercised here.

```powershell
.venv/Scripts/python.exe -m python.spikes.board_library `
  examples/compiled_board/rc_board.cir examples/compiled_board/pins.json `
  build/compiled-board-demo/rc_board `
  --engine build-spikes-current-vs18-20260906/Release/spikes_c_api.dll
```

The output directory must not exist. The exporter accepts bounded circuit data,
not user C++ source or free-form compiler flags; compilation has a 120-second
timeout. Files are staged in a sibling temporary directory and the package is
published only after compiler success. A failed build reports the first 16 KiB
of its log and does not publish a manifest. Select a new directory to rebuild.

To compile and execute the complete original firmware example in one command:

```powershell
.venv/Scripts/python.exe -m examples.compiled_board.build_and_run `
  --engine build-spikes-current-vs18-20260906/Release/spikes_c_api.dll `
  --output build/compiled-board-demo
```

This produces `rc_board/manifest.json`, the board library, `firmware.exe` on
Windows, and `firmware-output.txt` alongside the compilation logs.

The separate fault example compiles an actual NMOS/diode board, runs a linked
C++ consumer, compares a Python compiled-board consumer with separately built
native internal sessions, and exercises a scheduled replay and an explicitly
unverified environment mapping:

```powershell
python -m examples.compiled_board_faults.build_and_run `
  --engine build-spikes-faults-20261010/Release/spikes_c_api.dll `
  --output build/compiled-board-fault-demo
```

The package contains its DLL/shared library, public `board_library.h` C API,
`board_library.hpp` C++ RAII wrapper, generated board definition, runtime source,
owned engine C header, normalized circuit JSON, compiler log, Windows import
library, and `manifest.json`. The manifest records source, artifact, compiler,
engine and import-library hashes, limits, pin units and approximate model status.
Normalized source generation is deterministic; binary bit reproducibility across
toolchains and timestamps is not claimed. Engine binaries and their dependencies
are not redistributed by this command.

Compile `examples/compiled_board/firmware.cpp` with the package include directory
and `rc_board.lib` (Windows) or shared library (Unix). Put both the board and engine
directories on the trusted process DLL search path on Windows; Unix builds carry
the configured engine directory as a runtime search path. Distribute the exact
matching engine and its dependencies under their applicable licenses.

```cpp
#include "board_library.hpp"
spikes::Board board;
board.drive("dac", 3.3);
board.step(10e-6);
double adc_volts = board.read("adc");
double load_amps = board.read("load_current");
```

The Python loader additionally verifies package/engine hashes and checks the
actual imported engine function address against the selected engine before it
creates any board objects. A different engine already bound into the process
causes rejection; restart with a clean process and the intended dependency.
Hashes detect modification, not malicious authorship. Load only trusted packages.
Direct C/C++ consumers must authenticate their dependencies themselves; the C ABI
checks version compatibility and exposes `spikes_board_engine_identity()` for
host verification. Engine transitive dependency authentication remains with the
engine installation. Hash checks do not provide signatures or TOCTOU protection.

```python
from python.spikes.board_library_client import BoardLibrary

library = BoardLibrary("build/compiled-board-demo/rc_board/manifest.json",
    engine_library="build-spikes-current-vs18-20260906/Release/spikes_c_api.dll")
with library.create() as board:
    board.drive("dac", 3.3)
    board.step(1e-5)
    print(board.time_s, board.read("adc"), board.read("load_current"))
```

## Named bounded fault sites

`FaultSite` declares a case-sensitive name, exact element ID, supported
parameter (`resistance_ohm` or `threshold_voltage_v`), immutable healthy value,
finite minimum/maximum, and a mechanism label. `FaultBinding` either binds that
site to an existing ordinary resistor or NMOS Level-1 device, or explicitly
names the two existing nodes for a new shunt resistor. A shunt starts at its
finite healthy resistance; the compiler never guesses terminals from a device
name, mechanism label, schematic symbol, or layout.

The compiler rejects duplicate names/parameter bindings, unknown nodes,
one-terminal shunt declarations, mismatched healthy values, unsupported target
devices or parameters, and nonfinite/out-of-range values. The manifest and the
generated C descriptor table record the same site data. The Python client reads
both and rejects a mismatch, then exposes the sites through an immutable mapping.

```python
from python.spikes.board_library import FaultBinding
from python.spikes.fault_injection import FaultSite

faults = [FaultBinding(FaultSite(
    "drain_source_shunt", "FDS", "resistance_ohm",
    1e12, 1e-3, 1e12,
    "externally driven finite drain-source shunt"),
    "drain", "0")]

with library.create() as board:
    board.inject_fault("drain_source_shunt", 10.0)
    board.step(1e-6)
    board.clear_fault("drain_source_shunt")
    board.clear_all()
```

Injection and clearing alter a parameter for the next solve. They do not
recompute the last accepted outputs. A saved checkpoint includes current fault
parameters; restore replays them with electrical time/history. `reset()` creates
a healthy fresh session and clears the checkpoint. Instances remain isolated.
Invalid names/values leave the session unchanged.

The C ABI additions are `spikes_board_fault_api_version`, descriptor enumeration,
`spikes_board_inject_fault`, `spikes_board_clear_fault`, and
`spikes_board_clear_all_faults`; the Python/C++ wrappers expose `clear_all()`
and retain the explicit `clear_all_faults()` alias. Board ABI stays at version 1
because all additions are feature-gated.
Packages without `fault_injection_v1` retain the old engine dependency and load
path. A package declaring that feature requires both additive engine setters;
the Python loader checks them before loading the board DLL and reports the exact
missing symbols for an older engine.

## Electrical and temporal contract

- `AnalogInput` names a nonground circuit node, finite positive source resistance,
  initial voltage and finite minimum/maximum voltage. An internal voltage source
  connects through this resistance. Loading therefore causes a solved pin drop.
  Two inputs may intentionally drive the same node through their resistances.
- `BoardOutput` maps a name to a voltage node (V, referenced to ground) or element
  current (A, positive from its positive terminal toward its negative terminal).
  Outputs are the last accepted solution, not recomputed by a drive call.
- `drive()` holds its value until changed, with the change effective in the next
  accepted step. No GPIO direction/tri-state, interrupt queue, digital protocol,
  instruction-set emulator, or real-time scheduler is implicit.
- `step(dt)` performs one backward-Euler step. The manifest fixes minimum and
  maximum step, stop time, step count and convergence iteration/tolerance bounds.
  Invalid inputs leave the state intact. A rejected solve restores an internal
  checkpoint and returns a solver error. A caller must handle errors; there is no
  silent step-size adaptation or promotion of a failed result.
- Initialization uses the kernel's explicit capacitor voltage/inductor current
  conditions. No operating-point solve is requested. Use the first accepted step
  to obtain a solved resistive response; do not interpret initialization values
  as a DC operating point.
- `save()` replaces one saved checkpoint; `restore()` restores time, integration
  history, held source values, and edited fault parameters. `reset()` creates a
  fresh healthy instance and clears the checkpoint. RAII/context managers release
  owned sessions. Distinct objects have isolated states; serialize calls to any
  one object.
- Error messages and residual diagnostics remain available to the consumer.
  `spikes_board_error(NULL)` reports creation errors on the current thread.

Electrical fidelity is limited to the supplied lumped and bounded static-device
model. PCB parasitics, dynamic semiconductor charge/recovery, thermal/mechanical
behavior, component tolerances, peripheral registers and firmware binaries are
not inferred from a board layout. This is a
host-programmable circuit co-simulation object, not a whole-device emulator or
FMU. Package generation does not qualify a model or validate untested physics.

Finite shunts are externally commanded approximations. In the checked fault
fixture the NMOS bulk is explicitly tied to source, so a drain-source shunt can
be labeled as a body-diode/drain-source short approximation for that topology.
With an independently connected bulk, a body-junction fault must instead declare
the corresponding drain/body terminals. Neither case changes intrinsic diode
damage, reverse-recovery physics, or hidden device topology.

## Reproducible numerical checks

The original Apache-2.0 fixture connects the 3.3 V DAC through a 1 kohm source
resistance and 1 kohm board resistor to an ADC node with 2 kohm and 1 uF to ground.
The independently derived DC voltage is 1.65 V, terminal voltage 2.475 V, load
current 0.825 mA, and time constant `(2 kohm || 2 kohm) * 1 uF = 1 ms`.
For zero initial charge the continuous reference is
`v(t) = 1.65 * (1-exp(-t/0.001))`. Backward Euler at constant `h` gives the independent
recurrence oracle `v[n] = 1.65 * (1-(1+h/0.001)^(-n))`.

```powershell
$env:SPIKES_BOARD_ENGINE = (Resolve-Path build-spikes-current-vs18-20260906/Release/spikes_c_api.dll)
.venv/Scripts/python.exe -m unittest discover -s tests/python -p test_spikes_board_library.py -v
```

Run in the configured compiler environment. Without `SPIKES_BOARD_ENGINE`, only
the pure definition/rejection tests run; native tests are explicitly skipped.
Native checks cover analytical recurrence, first-order time-step refinement
against the continuous reference, drop/current polarity, isolated instances,
source/history restoration, reset, input and time bounds, artifact tampering,
and an actual compiled C++ firmware consumer that samples a 12-bit ADC and a
1 V threshold. The fault suite also checks exact generated/manifest descriptors,
normal/GS/DS/degraded/VTO results against direct native sessions, checkpoint
fault replay, clearing/reset, instance isolation, and rejection without mutation.
Test build folders remain on Windows because loaded DLLs cannot
be removed until their process exits. All fixture/source/oracle material here
was independently authored; no external implementation or model was copied.

## Retained local demonstration (2026-10-10)

The generated Windows x64 package is at
`build/compiled-board-demo/rc_board/manifest.json`, with `rc_board.dll`, its import
library and public headers beside it. `build/compiled-board-demo/firmware.exe`
is the actual linked consumer. Its measured output at 10 ms is ADC 1.64992 V,
pin 2.47496 V and load 0.824961 mA; sampled 1 V threshold detection is 0.94 ms.
The independent object remains at time zero. An explicit Python load of the same
package returns 0.016336633663366337 V after the first 10 us step, matching the
backward-Euler oracle.

The original compiler-enabled regression remains reproducible; raw output from
its retained package run is in `build/compiled-board-demo/native-verification.log`. Rebuild from
the checked-in fixture using `python -m examples.compiled_board.build_and_run`
with `--engine` and a new `--output` directory. These local build artifacts are
demonstration evidence, not a clean-machine release package.

The fault package is retained at
`build/compiled-board-fault-demo/fault_board/manifest.json`. The actual C++
consumer reports 4.2 V normal, 5.0 V with the 0.01 ohm gate-source shunt,
0.00049993 V with the 0.01 ohm drain-source shunt, 0.439443 V with the 10 ohm
degraded path, and 5.0 V at 6 V VTO. Direct native-internal and compiled Python
results agree to the recorded floating-point values in all five scenarios.
`environment-and-campaign.json` retains the explicitly unverified synthetic
dose-to-VTO mapping and the deterministic inject/clear replay trace. Eighteen
compiler-enabled board tests passed together (the original subset plus six new
compiled-fault/device tests, 20 total). These checks qualify this bounded fixture and API behavior;
they do not establish general damaged-device or environment-model validity.
