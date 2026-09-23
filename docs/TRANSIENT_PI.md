# Transient PI RLC Solver

## Scope

`spike.peec_rl_transient` is SPIKE's first geometry-derived time-domain PI
solver. The stable solver ID is retained for project compatibility; the current
implementation reports itself as `spike-peec-rlc-transient/v0.2`. It consumes
the same normalized `DesignIR`, topology-preserving hybrid conductor mesh,
terminal definitions, return-path model, and solver-plugin contract used by DC
and AC PI.

The implemented state equation is:

```text
R i(t) + L di(t)/dt - A^T v(t) = 0
A i(t) + C dv(t)/dt = j(t)
```

SPIKE integrates this equation with backward Euler. `R` is the extracted DC
conductor-resistance matrix plus explicit contact/package series resistance.
`L` is the full mutual partial-inductance matrix from the native PEEC runtime.
`A` is the branch/node incidence matrix. `C` is an optional nodal matrix built
from distributed branch capacitance to one reference conductor. Voltage sources
are imposed node boundaries and current sinks are time-varying KCL injections.

The capacitance path is deliberately limited. It estimates per-length
capacitance with a Hammerstad/Jensen-style microstrip relation using imported
dielectric thickness and epsilon. An explicit return net is preferred; without
one, the nearest copper layer is inferred per branch and the result is marked
accordingly. This is not a multi-conductor field-solved capacitance matrix.

## Supported Geometry

- Routed copper traces.
- Polygonal copper zones through the hybrid finite-volume mesh.
- Pads and pad-to-route/zone connectivity.
- Plated through vias and connected copper layers.
- Multiple sources and loads.
- Explicit supply/return loops and isolated local secondary references.
- Explicit contact and package series resistance.

## Waveforms

Sources and current sinks accept:

- Constant value.
- Step with initial value, delay, and finite rise time.
- Repeating pulse with low value, delay, rise, high time, fall, and period.
- Piecewise-linear `time:value` points.

For paired explicit returns, SPIKE derives the return-current waveform from the
positive sink and reverses its sign. The return cannot silently diverge from its
paired load.

An ideal zero-rise edge is allowed for exploratory work, but the report marks
its peak `L di/dt` as timestep-limited. Use measured or specified edge times and
at least five integration points across the fastest edge.

## Time Controls

- `stop_time_s`: total physical run time.
- `time_step_s`: maximum integration step. In automatic mode SPIKE recommends a
  step from the fastest source/load edge and the run window. SPIKE uses a
  uniform step that ends exactly at `stop_time_s`.
- `output_decimation`: saves one viewport/report frame every N integration
  steps. It does not change numerical integration.
- `output_decimation_mode`: `auto` may increase decimation to satisfy frame and
  memory limits; `manual` preserves the requested value and blocks unsafe runs.
- `playback_fps`: preferred UI/GIF playback speed; it does not change physics.
- `initial_condition`: `operating_point` or `zero` branch current.
- `max_solver_time_s`: wall-time limit covering extraction and integration.
- `memory_budget_mb`: conservative dense-workspace plus output-frame budget.
- `visual_sample_limit`: spatial sample limit for each stored animation frame;
  numerical integration still uses the complete extracted network.
- `capacitance_model`: `auto`, `stackup_shunt`, or `none`.

The bundled solver defaults to 50,000 internal steps, 1,000 saved frames, and a
2 GB transient workspace/output budget. Its source-connected branch capacity is
derived from that budget instead of a fixed global branch count. Preflight
reports the derived branch limit, recommended and effective timestep, frame
count, compact output bytes, memory budget, and mesh size. Runs fail if the
dense workspace cannot fit the selected memory budget or if
extraction/integration exceeds the wall-time limit.

## Matrix Passivity And Numerical Gates

Overlapping line filaments from traces, pads, zones, and via transitions can
make the approximate native partial-inductance matrix non-passive. Before time
integration, SPIKE eigendecomposes the symmetric matrix and applies the nearest
positive matrix in the Frobenius norm. Results record the negative eigenmode
count, original eigenvalue range, eigenvalue floor, and correction ratio.

- Any correction is reported as `TRANSIENT_INDUCTANCE_PASSIVITY_PROJECTED`.
- Corrections above 5% are explicitly described as large and qualitative.
- Corrections above 50% fail with `TRANSIENT_INDUCTANCE_NONPASSIVE`.
- Non-finite states, states above the numerical safety bound, and scaled linear
  residuals above `1e-7` fail rather than producing result fields.

Passivity projection makes the exploratory R-L integration stable; it does not
validate the underlying filament discretization. Quantitative use still
requires geometry cleanup, mesh-convergence comparison, and independent
analytical or measured fixtures with a small correction ratio.

## Result Contract

The solver emits `spike/v1` with:

- Timestamped absolute voltage and source-relative drop fields.
- Timestamped branch current, current density, copper loss, and via stress.
- Timestamped current-density vectors.
- Static solver mesh aligned to imported board coordinates.
- Probe voltage/drop/current/density values and probe time histories.
- Peak voltage drop, overshoot, current density, current, copper loss, and
  branch `L di/dt` summary values.
- Integration, mesh, model-limit, and solver provenance.
- Matrix passivity correction and maximum scaled linear residual.
- Stackup capacitance provenance, reference layers, skipped branches, and
  displacement-current peaks when that model is active.
- Estimated dense workspace, peak worker memory, actual dense-array bytes,
  compact time-series bytes, and solver wall time.

Time history uses `spike/compact-field-series/v1`: coordinates, layer/net/kind
metadata, and vector directions are stored once, while each frame stores only
numeric scalar/vector arrays. The desktop materializes the active frame on
demand. This keeps the project/result bundle bounded without changing solver
resolution.

The desktop consumes these frames with synchronized 2D and 3D overlays,
animation slider, playback controls, stable time-global color ranges, flat or
height-map rendering, independent board/model visibility, analyzed-net-only
inspection, and offline GIF export.

## Validity Boundary

This mode is `Approximate` and `Experimental`. It does not include:

- A field-solved multi-conductor capacitance matrix or via capacitance.
- Dielectric loss, dispersion, or transmission-line propagation delay.
- Nonlinear semiconductor models.
- Regulator control-loop dynamics.
- Inferred component/package RLC beyond assigned series resistance.
- Full-wave radiation, electric fields, or dielectric resonances.

Voltage/current edges excite the extracted RLC approximation, but waveform
motion must not be interpreted as full-wave propagation. Closed-loop switching,
component-accurate decoupling response, nonlinear ringing, and device stress
require assigned component models and the geometry-derived network plus SPICE
co-simulation path.

## CLI

Create a request without running it:

```powershell
python -m python.spike_core setup-transient board.kicad_pcb `
  --net VCC `
  --source "0,0,F.Cu,5" `
  --load "10,0,F.Cu,1" `
  --load-waveform "step,0,2e-6,1e-6" `
  --stop-time-s 8e-6 `
  --output-decimation 5 `
  --output-decimation-mode auto `
  --memory-budget-mb 2048 `
  --max-solver-time-s 120 `
  --capacitance-model auto `
  --visual-sample-limit 12000 `
  --save-request transient-request.json
```

Omit `--time-step-s` to use the excitation-based recommendation. Supply it to
force a manual maximum step.

Use `analyze-transient` (alias `transient`) with the same arguments to run
preflight and solve. `constant`, `short-pulse`, `long-pulse`, `step`, `pulse`,
and `pwl` waveform forms are accepted.
