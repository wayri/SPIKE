# SPIKE Command-Line Interface

The SPIKE CLI is the headless interface to the same normalized design model,
solver registry, validation rules, and result contracts used by the desktop
application. It runs locally and does not require network access or the GUI.

## Launch

From a source checkout:

```powershell
.\spike.cmd --version
.\spike.cmd --help
```

The equivalent portable Python invocation is:

```text
python -m python.spike_cli --help
python -m python.spike_core --help
```

Packaged releases can expose the same interface as `spike.exe`.

## Preflight and mesh preview

```powershell
spike preflight spike-analysis-request.json
spike --output mesh-preview.json mesh-preview spike-analysis-request.json
```

Both commands run without solving. Preflight returns a non-zero analysis exit
code when the request cannot be solved.

## Experimental hybrid PEEC RL extraction

```powershell
spike analyze-ac board.kicad_pcb `
  --net VCC `
  --start-hz 1e3 `
  --stop-hz 1e8 `
  --points 101 `
  --source 20.5,14.0,F.Cu,regulator `
  --load 112.0,40.0,B.Cu,load `
  --mesh-size-mm 1 `
  --zone-cell-mm 0.5 `
  --memory-limit-gb 2 `
  --via-plating-mm 0.025
```

This command extracts port-referred resistance and partial inductance from a
single topology containing traces, pads, copper zones, plated vias, and
through-pad barrels. AC port syntax is `X,Y,LAYER[,NAME]`; source and load can
be omitted for exploratory extraction, in which case inferred endpoints are
reported as approximate. Capacitance, dielectric loss, proximity effect,
roughness, and S-parameters are not yet included. See `SOLVER_STATUS.md`.

## Touchstone and network analysis

Inspect a Touchstone network, serialize S-parameter traces, calculate matched
input impedance and group delay, and run passivity/reciprocity checks:

```powershell
.\spike.cmd sparam-inspect .\channel.s4p --trace-limit 1000
```

Renormalize a network to a new real reference impedance:

```powershell
.\spike.cmd sparam-renormalize .\channel.s2p `
  --to-ohms 75 `
  --format RI `
  --touchstone-output .\channel-75ohm.s2p
```

The command does not silently claim causality. Causality workflows require an
explicit DC, resampling, window, and delay-removal policy.
The dense PEEC adapter derives its branch admission limit from
`--memory-limit-gb` and detected physical RAM. The minimum solver allowance is
2 GB. `--max-conductors` remains available as an optional stricter cap. The
resolved allowance, estimated dense workspace, and admitted branch limit are
written to result provenance. Raising this limit increases capacity; it does
not promote the solver beyond its declared experimental validity tier.

## PDN target and capacitor screening

Review an extracted impedance result and screen a simple direct-port bank:

```text
spike --output pdn.json pdn-review ac-result.json \
  --target-ohm 0.05 --net VCC \
  --candidate bulk,100e-6,0.01,1e-9,2
```

For explicit mounting paths or geometry-aware candidate ports, use a
versioned JSON candidate set:

```text
spike --output pdn.json pdn-review ac-result.json \
  --target-ohm 0.05 --net VCC \
  --candidate-file candidate-locations.json
```

`schemas/pdn-candidate-set-v1.schema.json` defines the exchange contract.
Location-specific screening requires reviewed local and transfer-impedance
sweeps on the same frequency grid. See `PDN_SCREENING.md`; coordinates alone
are never converted into an impedance or an "optimal" placement. Versioned
wrappers must declare `spike/pdn-candidate-set/v1`; raw arrays and single
candidate objects are accepted for automation convenience. Each review is
bounded to 4,096 candidates.

## Solver benchmarks

```text
spike benchmark
spike --output benchmark-report.json benchmark
```

The command returns nonzero when any analytical, convergence, or native hybrid
fixture fails, making it suitable for local validation and CI.

## Discover and inspect

```text
spike solvers
spike solvers --available
spike capabilities
spike dependencies
spike extensions

spike inspect board.kicad_pcb
spike inspect board.kicad_pcb --section nets
spike validate board.kicad_pcb
spike --output board.designir.json import board.kicad_pcb
spike --output vcc.geometry.json extract-net board.kicad_pcb --net VCC
```

Inputs can be native KiCad boards, normalized `DesignIR` JSON, an analysis
request containing DesignIR, or a SPIKE project package containing embedded
KiCad source.

## DC analysis

Terminal syntax is:

```text
X,Y,LAYER,VALUE[,CONTACT_RESISTANCE[,PACKAGE_RESISTANCE]]
```

Source values are volts. Load values are amperes. Resistances are ohms.
`--source`, `--load`, and `--net` are repeatable.

```text
spike --output result.json analyze-dc board.kicad_pcb \
  --net 24Vaux \
  --source 20.5,14.0,F.Cu,24,0.002,0.008 \
  --load 85.0,42.5,F.Cu,1.2,0.003,0.012 \
  --load 112.0,40.0,B.Cu,0.8 \
  --zone-cell-mm 0.5 \
  --max-zone-cells 12000 \
  --max-drop-mv 80 \
  --max-density 75 \
  --save-request reproducible-request.json
```

The DC engine includes tracks, vias, pads, copper zones, pad spreading,
through-pad barrels, and assigned contact/package resistance. Zone results are
approximate until a mesh-convergence comparison passes.

## Transient PI analysis

Transient PI uses the same terminal syntax and connected-conductor geometry as
DC analysis. It solves extracted resistance, the full partial-inductance
matrix, and optional stackup-derived single-reference capacitance with
backward-Euler time integration. Configure numerical time resolution, saved
frame rate, runtime, and memory independently:

```text
spike --output transient-result.json analyze-transient board.kicad_pcb \
  --net 24Vaux \
  --source 20.5,14.0,F.Cu,24,0.002,0.008 \
  --load 85.0,42.5,F.Cu,1.2,0.003,0.012 \
  --load-waveform pulse,0.1,100e-6,2e-6,300e-6,2e-6,1e-3 \
  --stop-time-s 2e-3 \
  --output-decimation 10 \
  --output-decimation-mode auto \
  --playback-fps 20 \
  --initial-condition operating_point \
  --memory-budget-mb 2048 \
  --max-solver-time-s 120 \
  --capacitance-model auto \
  --visual-sample-limit 12000 \
  --save-request transient-request.json
```

Waveform forms are:

```text
constant
step,LOW,DELAY,RISE
pulse,LOW,DELAY,RISE,HIGH_TIME,FALL,PERIOD
pwl,T0:V0;T1:V1;...
short-pulse
long-pulse
```

Repeat `--source-waveform` or `--load-waveform` once per terminal, or provide a
single waveform to broadcast it to every source or load. `setup-transient`
creates a reproducible request without running it. Omit `--time-step-s` for an
excitation-based recommendation, or provide it for manual control. Automatic
output decimation preserves integration resolution while increasing the saved
frame interval when the frame count or memory budget requires it.

The installed transient solver is an experimental quasi-static conductor RLC
model. It captures geometry-derived resistance, mutual partial inductance,
contact/package resistance, current redistribution, inductive voltage
excursions, and approximate line-to-reference displacement current. It does not
model via capacitance, dielectric loss/dispersion, full-wave propagation,
nonlinear devices, or source-control dynamics. These limitations are included
in result provenance and generated reports. Results also record passivity
correction, linear residuals, solver wall time, estimated/actual memory, compact
frame storage, and capacitance-reference provenance; non-finite, divergent,
time-limited, or over-budget runs fail.

## Requests, projects, and batches

Run a saved request or SPIKE project:

```text
spike --output result.json run reproducible-request.json
spike --output result.json run board-review.spike.json
```

A batch manifest uses the standard request unchanged:

```json
{
  "contract": "spike/analysis-batch/v1",
  "jobs": [
    {
      "id": "24v-nominal",
      "contract": "spike/analysis-request/v1",
      "design": {},
      "spec": {}
    }
  ]
}
```

```text
spike --output batch-result.json run batch.json --continue-on-error
```

## Reports and revision gates

```text
spike report result.json --report-format html --report-output report.html
spike report result.json --report-format csv --report-output edge-results.csv
spike compare baseline.json candidate.json --tolerance-percent 2
```

Comparison returns a nonzero status when the candidate exceeds the configured
positive regression tolerance.

## EMI setup and screening

Validate a versioned EMI setup without running field physics, then rank the
selected nets from explicitly supplied pre-pass metrics:

```text
spike --output emi-preflight.json emi-preflight board.kicad_pcb emi-setup.json
spike --output emi-screening.json emi-screen board.kicad_pcb emi-setup.json
```

The design argument may be a KiCad board, DesignIR JSON, or SPIKE project. The
setup must use `spike/emi-setup/v1`. Screening is labeled `screening_only`; it
does not calculate radiation or establish compliance. See `EMI_WORKFLOW.md`.

## Output and exit codes

Global output options appear before the command:

```text
spike --output result.json --quiet analyze-dc ...
spike --output-format text inspect board.kicad_pcb
spike --compact capabilities
spike --fail-on-warning analyze-dc ...
```

Exit codes:

- `0`: successful command, completed analysis, or passing comparison.
- `1`: invalid arguments, input, or command execution.
- `2`: blocked/failed analysis or detected regression.
- `3`: design validation failed.
- `4`: warning encountered with `--fail-on-warning`.

Every machine-facing result is JSON by default. Solver provenance, model
status, assumptions, issues, and geometry counts remain present for CI and
auditability.
