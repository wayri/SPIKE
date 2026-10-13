# Co-simulation and digital twins

Verification and full-suite limitations are recorded in
[the implementation evidence](validation/COSIMULATION_DIGITAL_TWIN_20261010.md).

## Scope and implementation plan

Current scope is offline operation: local solver execution, file-based model
exchange, recorded measurement import/replay and local comparison reports.
Live telemetry, network acquisition, cloud execution, device control and
hardware-in-the-loop are deferred outside this workstream.

SPIKE already implements reviewed PEEC/native MNA fixed-point coupling and
specialized electrical/thermal coupling. Preserve those engines and their
qualification limits. This feature adds a separate experimental scalar
communication master and offline prediction/telemetry comparison. It does
not turn existing solvers into time-steppable participants automatically.

| Stage | Deliverable | Acceptance gate | State |
| --- | --- | --- | --- |
| 1 | Versioned fixed-grid master, explicit ports, replay/gain adapter registry, recorded twin comparison, CLI/worker and desktop script templates | Independent scheduling/residual oracles, malformed-input and failure checks, bounded reproducible examples | Implemented |
| 2 | Session adapters for SPIKES transient and retained thermal stepping | State initialization/reset, independent reference trajectory, communication-step refinement, energy balance and cancellation evidence | Planned |
| 3 | FMI co-simulation process adapter | Explicit supported FMI version, variable/unit admission, capability negotiation, packaging/license review, rollback/error/event handling and comparison with independent FMUs | Planned |
| 4 | Portable twin study inside project packages and dedicated editor | Geometry/model revision binding, stale withholding, atomic save/restore, disabled/error/recovery states | Planned |
| 5 | Offline recorded sensor import and replay | Recorded clock origin and uncertainty, unit conversion provenance, bounded files and hardware reference measurements | Planned |
| 6 | Offline calibration proposals | Reviewed parameter changes and held-out recorded-data validation | Planned |
| 7 | Live acquisition, device integration and hardware-in-the-loop | Separate scope, real-time deadline measurements, disconnect handling and independent hardware protection | Deferred |

Stages 2-6 remain offline and require separate implementation and evidence before capability
claims. Recorded comparison is the initial digital twin support; it is not
an autonomous operational twin or a validated hardware model.

## User workflow

Run the checked-in, synthetic example from the repository root:

```powershell
python examples/cosimulation/run_demo.py
python -m python.spike_core.cli cosimulation-catalog
python -m python.spike_core.cli cosimulation-run examples/cosimulation/coupled-replay.json
python -m python.spike_core.cli digital-twin-compare examples/cosimulation/recorded-twin.json
```

CLI inputs are raw versioned requests. Worker calls take `{"request": ...}`.
In the desktop, open Python Workspace, Templates, **Co-simulation and twins**.
Set `REQUEST_FILE` to a JSON file containing the worker parameter object and
run the selected template. It prints evidence in script output. Templates
start with no file selected, and results are not published as board analysis
fields. The script worker keeps execution off the webview thread.

Use `run_cosimulation`, `compare_digital_twin` or `cosimulation_catalog` through
`SpikeAutomation.call` for automation. Both CLI commands return a nonzero exit
code on rejected/failed/cancelled/timed-out results. Threshold violations are
reported data; `completed` means comparison executed, not that a model passed.

## Co-simulation API and equations

`python/spike_core/cosimulation.py` owns `run_cosimulation(request, *, adapters,
cancelled, timeout_s)`. Request schema: `schemas/cosimulation-request-v1.schema.json`.
Participant IDs, model revisions, scalar port directions, unit labels, initial
outputs and adapter configuration are explicit. Each input has exactly one
driver. Units must match exactly; there is no implicit conversion, vector
signal, inferred connection or EDA parser dependency.

The communication grid is `t[k] = k * step_s`, for `k=0..steps`. All initial
outputs are supplied at zero. At tick k, every participant reads the accepted
outputs at k-1. All next outputs and JSON states are staged, then accepted
together. Reordering participant declarations cannot change values. Feedback
cycles are allowed because every link has an explicit communication delay;
there is no algebraic loop solve or same-tick feedthrough.

The replay adapter supplies `config.values[k-1]` at tick k. The gain adapter
implements `y[k] = gain * u[k-1]`, with dimensionless gain and equal input/output
units. These are synthetic orchestration adapters, not physical solvers. The
test oracle with source values 1 initially, then 2,3,4 and gain 2 yields output
0 initially, then 2,4,6. Two unit-gain feedback participants swap initial values
on each tick. These independent discrete recurrences require no integration or
convergence tolerance; they do not demonstrate continuous coupling accuracy.

To add a trusted adapter, pass a registry dictionary mapping an adapter ID to
an object with `version`, `validate(participant, steps)` and
`step(participant, inputs, state, tick, time_s, step_s) -> (outputs, state)`.
The master copies the request once, supplies recursively read-only participant
configuration (arrays become tuples), copies state per tick, and checks exact output ports
and finite values. Adapters must keep state in the returned JSON value and avoid
external side effects: the master cannot roll back adapter-owned external state.
The default worker only admits the built-in replay/gain registry. JSON cannot
load Python code, commands or solver executables.

Resource limits: 8 MiB worker request/result, 64 participants, 32 ports per
direction, 10,000 steps and 200,000 retained scalar output values. Conservative
retained-frame byte admission may further reduce the permitted run size when
identifiers are long. Digital twin admission permits 128 channels and 10,000
samples per series, subject to the 8 MiB JSON limit and 500,000 values per series.
Timeout and cancellation are checked before callbacks and before tick acceptance. Callbacks
must bound their own work; hard termination belongs to the worker process host.
Failure returns only prior accepted frames, a structured issue and a failure
status. Those frames are diagnostic partial history, not a completed prediction.
Runs have fresh state; checkpoint/restart and adapter resource lifecycle hooks
are not implemented. There is no adaptive communication step or shortened final
step: specify an integer number of fixed steps.

## Digital twin API and provenance

`compare_digital_twin(request)` in `digital_twin.py` takes a model ID/revision,
supplied model status, channel IDs/units/absolute tolerances and independently
declared prediction and telemetry series. Each series repeats the model identity,
channel units and strictly increasing nonnegative `time_s` samples. Every sample
contains exactly the declared scalar channel values. A model revision should
identify the complete reviewed geometry, parameters and solver configuration;
the application does not infer or verify that revision from a board in this stage.
The digest binds the exact request, not the truth of the supplied identity.

Only exactly equal timestamps are matched. Export both series using a shared
clock/grid; `0.3` and `3 * 0.1` may differ in floating-point representation.
Non-overlapping series reject. Unmatched samples are counted. For each channel,
residual is measured minus predicted, maximum absolute error is `max(abs(r))`,
RMSE is `sqrt(sum(r*r)/N)` (evaluated with scaling to avoid squared overflow), and
violations count `abs(r) > tolerance`. Equality to tolerance is accepted. Traces
retain at most the first 2,048 matches per channel, reduced evenly to a total
budget of 20,000 trace points across channels; all matches contribute to
metrics, with truncation reported. Tolerances use the channel unit.

The fixture residuals 0.1 and -0.3 V give max error 0.3 V and RMSE
`sqrt(0.05)` V. All fixtures and oracles are independently authored synthetic
SPIKE material under Apache-2.0. No external models, data or implementations
were imported. There are no new dependencies. Request SHA-256 uses UTF-8 JSON
with sorted object keys, compact separators and finite numbers. Array order
remains significant. Model status is preserved as a supplied claim; residual
agreement cannot promote experimental/approximate/unsupported physics.

Recovery: fix the reported identity/unit/time/port issue and rerun a fresh
request. No inputs, project files or device settings are mutated. Keep raw
telemetry and its acquisition provenance outside this initial comparison;
sensor uncertainty, time alignment, offline calibration and local FMI adapters
remain planned. Online acquisition and real-time/HIL control are deferred.
