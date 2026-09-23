# SPIKES HDL, Verilog-A, and OSDI frontend

Status: real compiler invocation, package validation, first-class trusted C++
OSDI 0.3 DC registration, and a separately qualified Windows AppContainer
worker for hostile OSDI DC evaluation. Reactive/transient, AC, noise, limiting,
and OSDI 0.4 callbacks remain open.

`python/spikes/hdl_frontend.py` distinguishes four separate capabilities that
must not be conflated:

1. discovering an installed compiler;
2. compiling exact, content-addressed source with a policy-generated command;
3. validating an exact OSDI package and callback declaration; and
4. loading and executing model callbacks inside the native MNA solver.

All four boundaries are implemented for the declared OSDI 0.3 DC subset.
`spikes::load_trusted_osdi_0_3_device` loads a reviewed module, validates its
descriptor and offsets, and registers its resistive residual/Jacobian directly
as a native C++ MNA element. A separate out-of-process route invokes the same
bounded callback subset without routing through ngspice.

## Supported compiler policies

| Tool | Input | Result |
| --- | --- | --- |
| OpenVAF | Verilog-A (`.va`, `.vams`) | OSDI artifact |
| Icarus Verilog | Verilog/SystemVerilog (`.v`, `.sv`) | VVP artifact |
| Verilator | Verilog/SystemVerilog | lint attestation |
| GHDL | VHDL (`.vhd`, `.vhdl`) | analysis attestation |

The frontend searches the local `PATH`; it never downloads a compiler. A
compile plan binds the compiler binary, source, language, top module, output
kind, and complete plan by SHA-256. Arguments come from fixed per-compiler
templates, `shell=False` is used, the child receives a minimal environment and
temporary directory, and time/output/artifact bounds are enforced. Compiler
results still report `loadable_by_spikes_solver: false`: compilation alone is
not model qualification. A verified manifest and native callback qualification
are separately required.

An OSDI module manifest binds artifact, source, and compiler digests, ABI
version, module identity, and required callback declarations (`setup`, `load`,
`noise`, `trunc`, `accept`, and `destroy`). Validation does not `dlopen` the
artifact and therefore cannot execute initialization code.

## Local compiler inventory

Reviewed workspace-vendored binaries are now explicitly discovered by path and
SHA-256: OpenVAF 23.5.0, GHDL 6.0.0, Icarus Verilog 14 development, and
Verilator 5.051. All four compile, analyze, or lint the first-party CC0
fixtures in `benchmarks/hdl`. Icarus uses the checksummed standalone Windows
package and the package-required joined `-B<ivl-directory>` argument. The
machine-readable report is
`artifacts/spikes-hdl-toolchain-qualification-wave6-final-2026-08-31.json`.

OpenVAF's MSVC linker and GHDL's PATH-resolved MinGW runtime DLLs are also
discovered and hashed as auxiliary executables. Compile plans therefore do not
silently inherit an arbitrary linker or runtime identity.

## Isolation boundary

The direct C++ registration route executes module initialization and callbacks
inside the solver process. It is therefore restricted to trusted,
digest-reviewed models. It must never be selected for hostile code.

On Windows, `hostile_code=True` instead requires exact digest-bound native
worker and launcher executables. The model and worker are copied into a fresh
staging directory. The launcher creates the worker in a zero-capability
AppContainer, grants the AppContainer SID access only to staged entries, and
places it in a Job Object with a one-process and 512 MiB limit plus
kill-on-close. Zero capabilities deny network access. No caller-supplied path
outside the staging directory receives an ACL grant.

`python/spikes/osdi_runtime.py` contains two executable, digest-bound routes.
`NativeOsdiCallbackRuntime` copies the exact model and a digest-bound minimal
worker into a fresh temporary directory, launches the worker with Python
isolated mode (`-I -S`), validates OSDI ABI 0.3 and descriptor bounds, invokes
the native DC callbacks, rejects non-finite stamps, and returns residual and
Jacobian entries to SPIKES. The first-party 1 kOhm OpenVAF fixture produces
`[1 mA, -1 mA]` and the expected four-entry conductance Jacobian at 1 V. The
machine-readable result is
`artifacts/spikes-osdi-native-qualification-wave6-2026-08-31.json`.

The AppContainer route uses `spikes_appcontainer_launcher` and
`spikes_osdi_worker`. Its retained qualification runs a real OpenVAF resistor
callback and independent probes that attempt to read a forbidden sibling file
and open a TCP socket. Windows returns `ERROR_ACCESS_DENIED` and `WSAEACCES`,
respectively. Evidence is
`artifacts/spikes-appcontainer-osdi-qualification-2026-08-31.json`.

`NgspiceOsdiSandboxRuntime` is the separate compatibility-host route. It
injects the only permitted `pre_osdi` directive into an otherwise screened
self-contained deck and runs ngspice in the bounded process worker.

The route was exercised with the real OpenVAF-generated resistor artifact. The
vendored ngspice 46 binary rejects `pre_osdi` as an unrecognized device/model
line, so this particular build does not expose the required OSDI command and no
model callback executed. This is retained as a tested host-capability blocker,
not described as successful compatibility-host OSDI support.

The older Python-worker and ngspice compatibility routes retain Windows Job
Object containment but are not hostile-code routes. On non-Windows hosts,
`hostile_code=True` remains fail closed until an equivalent OS-enforced policy
is implemented and independently qualified. The AppContainer qualification is
specific to the staged OSDI 0.3 DC worker; it does not make arbitrary compiled
blocks or in-process OSDI safe.

Run the focused verification with:

```powershell
python -m unittest tests.python.test_spikes_hdl_frontend tests.python.test_spikes_osdi_runtime -v
python scripts/run_spikes_osdi_native_qualification.py
python scripts/run_spikes_appcontainer_osdi_qualification.py
```
