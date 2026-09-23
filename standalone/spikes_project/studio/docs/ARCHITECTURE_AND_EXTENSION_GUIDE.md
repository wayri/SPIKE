# SPIKES architecture and extension deployment guide

Status: source-tree engineering guide, 7 September 2026. This is not a claim of
SPICE3 parity, universal vendor-model compatibility, field-solver accuracy or
hard-real-time certification. Installed applications can lag this source tree.

## 1. Runtime boundaries

| Layer | Source | Responsibility and boundary |
|---|---|---|
| Native engine | `src/spikes`, current `spikes_c_api.dll` / `libspikes_c_api.so` | Owned C++ circuit numerical core; supported requests only |
| Python integration | `python/spikes/native_abi.py`, `cli.py` | Request validation, explicit native-library selection, JSON results |
| Netlist frontend | `python/spikes/netlist.py` | Supported syntax to normalized project; rejection is preferable to silently approximating unsupported devices |
| Desktop | `standalone/spikes_project/studio/python/spikes_studio` | wx editor, document transactions, probes, Matplotlib plots, run coordination |
| Library metadata | `library_package.py`, `component_catalog.py` in desktop package | Data-only `.spklib` import/export; generic presets are not qualified manufacturer parts |
| Device contracts | `python/spikes/device_contracts.py`, `device_extensions.py` | Metadata, bounded registration, reference behavior; registry does not load native code |
| Compiled blocks | `python/spikes/compiled_blocks.py`, desktop `controller_block.py` | Separate existing protocols; trusted code only, not a hostile-code sandbox |
| Mixed package inspection | `python/spikes/mixed_library.py` | New manifest/path/hash validation; no runtime linking or execution |

The parent SPIKE application's `extension_sdk` and `solver_sdk` are separate
integration surfaces. Their process extensions are not automatically compatible
with standalone SPIKES Studio. Never assume parent-app plugins ship in the simulator.

Data flow: editor/netlist → validated project → selected analysis/backend → result
and provenance → plots, probes, reports. Python reference analyses and native C++
analyses are distinct backends; record which one produced a result.

## 2. Embedding and CLI

From the repository root, these are actual CLI entry points:

```powershell
python -m python.spikes --help
python -m python.spikes check examples/spikes/studio_tutorials/01_dc_divider.cir
python -m python.spikes native-run examples/spikes/studio_tutorials/02_rc_startup.cir --library build-spikes-current-vs18-20260906/Release/spikes_c_api.dll --method bdf2 --probe "V(out)" -o result.json
python -m python.spikes library-inspect my-library/library.json -o inspection.json
```

CLI exit codes: 0 success, 2 input error, 3 solve error. Inspect command-specific
`--help` before automation. Integrators should invoke argument arrays, not shell
strings; retain stderr, exit code, exact deck, library hash and result together.
An invalid package must not advance to a compiler or loader.

Use the Python native ABI wrapper for in-process scripting with an explicitly
selected engine binary. Use process-based CLI jobs when crash separation matters.
Neither process separation nor an explicit trust flag prevents filesystem/network
access by hostile code. External applications must add an OS-enforced sandbox if
they accept untrusted models.

For closed-loop controllers, distinguish simulation time from wall time. A future
general co-simulation protocol needs initialize, advance-to-time, exchange, snapshot,
restore and terminate operations, with units, time ownership and algebraic-loop
policy. Do not treat batch reruns as state-preserving co-simulation. Existing desktop
controller support is narrower; physical PIL/HIL timing and fail-safe qualification
remain outstanding.

## 3. Mixed-library package v1

Keep a directory containing `library.json` and relative payload files. Example
manifest (replace the hash with the actual SHA-256 before inspection):

```json
{
  "contract": "spikes/mixed-library/v1",
  "id": "example.motor-drive",
  "version": "1.0.0",
  "license": "MIT",
  "modules": [
    {
      "id": "bridge",
      "kind": "spice",
      "domains": ["electrical"],
      "path": "models/bridge.cir",
      "sha256": "REPLACE_WITH_64_HEX_DIGITS"
    }
  ]
}
```

Kinds: `spice`, `equations`, `c`, `cpp`, `verilog`, `vhdl`, `dll`. Domains:
`electrical`, `magnetic`, `thermal`, `mechanical`, `digital`. Multiple modules and
domains can coexist. The current inspector checks integrity only, not model syntax,
pin compatibility, licensing rights or numerical validity. It limits manifests to
1 MiB, modules to 256 and payloads to 64 MiB. Absolute paths, traversal, linked
payloads, missing files, duplicate IDs and incorrect hashes are rejected.

`execution_enabled` is always false. A DLL hash is not proof that a DLL is safe.
This format does not auto-register DLLs, compile HDL or join module ports. It is
separate from the GUI's data-only `.spklib`; the GUI does not yet import mixed bundles.
Do not modify a bundle concurrently with inspection; verification is not a secure
loader or a defense against filesystem races.

The next executable contract must specify ABI version, platform/architecture,
compiler/runtime requirements, ordered pins, units, state variables, residual and
Jacobian interfaces, charge/flux contributions, noise, event surfaces, initialization,
rollback, dependency ordering and validity envelopes. Equations must use a bounded
expression language, not unrestricted Python evaluation. Module composition requires
explicit port connections and energy/sign conventions, not matching names alone.

## 4. Magnetics and mechanical integration specification

This section defines required modeling behavior, not newly implemented native devices.
Circuit-level models can include geometry-derived parameters without solving STEP
files or TCAD. 'Full physics' is not a single accuracy switch: every approximation
requires a stated frequency, temperature, current and geometry validity range.

For a linear winding system, use `v = R i + d(lambda)/dt`, `lambda = L i`.
Mutual terms are `Mij = kij sqrt(Li Lj)` with explicit dot polarity. Require the
complete inductance matrix to be symmetric positive semidefinite for passive models;
pairwise `abs(k)<=1` is necessary but not sufficient for many windings.
Leakage and magnetizing inductance must not be counted twice.

For nonlinear cores, use flux linkage from a magnetic circuit or fitted constitutive
law with differential reluctance and consistent derivatives. Flux density is
`B = Phi/Ae`; `Ae`, path length, gap and turns need provenance. Hysteresis needs
internal state and rollback on rejected timesteps. A single-valued saturation curve
cannot reproduce remanence or loop loss. Core loss laws require calibrated waveform,
frequency and temperature ranges; an arbitrary Steinmetz fit is not universal.

Planar/toroidal/ferrite/flyback variants need winding geometry, material curves,
gap/fringing assumptions, DC resistance, skin/proximity loss and winding-to-winding
and winding-to-core capacitance. Interleaving changes both coupling and capacitance.
Temperature estimates need an explicit thermal network and boundary conditions,
not a display label. Report flux, B, leakage energy, copper/core loss, temperatures,
incremental inductance and saturation margin with model provenance.

Connection topology is separate from core physics:

| Connection | Required representation |
|---|---|
| Y–Y | Three phase windings each side; explicit neutral accessibility/grounding |
| Y–delta / delta–Y | Ordered winding polarities, delta loop and specified vector group |
| Delta–delta | Both loops explicit; internal circulating currents observable |
| Autotransformer | Shared tapped winding and conductive path; never claim galvanic isolation |
| Multiphase / zigzag | General winding incidence matrix and explicit phase order |

Do not infer phase displacement from the words star/delta alone. Zero-sequence
behavior depends on core construction and neutral paths. Grid-scale transformer
qualification needs inrush, residual flux, short-circuit leakage, unbalance and
circulating-current cases in addition to a balanced sinusoidal ratio check.

Mechanical ports need energy-consistent force/velocity or torque/angular-velocity
pairs. Derive force/torque from a consistent energy or co-energy potential (with the
correct held variables); include inertia, damping, constraints and initial state.
Validate electrical input = stored-energy rate + mechanical output + thermal loss
within declared numerical tolerance. Motors/actuators cannot be qualified by plotting
an arbitrary torque equation alone.

## 5. UI, results and reproducibility

Desktop documents retain source and editor metadata, with undoable changes. Autosave
uses separate recovery snapshots and does not overwrite originals. Run sequences are
finite serial jobs with separate results, not a parallel or state-handoff scheduler.
Plots may decimate display points; measurements must use retained source samples.
Thermal margin reports distinguish measured/model-provided temperature from explicit
steady-state user assumptions and cannot establish lifetime or certification.

Model fidelity inheritance (schematic → subsheet → part), enforced overrides and
equivalent-circuit previews are requested future work, not implemented by this guide.
Record effective model tier, parameter values, parasitics and source hashes with each
run when that feature is implemented; never silently substitute an 'ideal' device.

## 6. Independent distribution and qualification

Build entry point: `scripts/build_spikes_studio_package.py --help`; native packaging
CMake project: `scripts/studio_packaging/CMakeLists.txt`. Desktop launcher:
`scripts/launch_spikes_studio.py`. Documentation and `examples/spikes` are copied by
future package builds. Existing installers do not acquire new files automatically.
Ship runtime dependencies, native library, schemas, examples, help, notices and
redistribution licenses together. The separate `SPIKES-Independent` directory may
be stale: regenerate and verify before treating it as a release source archive.

Release gates should include clean-host Windows/Linux launch, native ABI smoke,
parser rejection tests, analytical DC/RC/RL traces, library corruption tests, GUI
interaction tests, and equal-model/tolerance cross-engine checks. Add magnetic energy
balance, passive matrix validation, phase/vector-group checks, core-loss/thermal
measurement comparisons and controller determinism before advertising those domains.

Current evidence does not establish superiority over ngspice/LTspice, universal
manufacturer support, or physical hard-real-time operation. Full vendor compact
models, general mixed-module execution, calibrated coupled magnetic DAEs and a
hostile-code sandbox remain substantial development and qualification work.
