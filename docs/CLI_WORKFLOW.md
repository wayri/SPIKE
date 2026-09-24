# SPIKE CLI Workflow

The CLI uses the same DesignIR, AnalysisSpec, preflight, solver, and report
contracts as the desktop application. Commands run locally and do not require a
network connection.

Run commands from the SPIKE repository root.

## 1. Import And Inspect

```powershell
python -m python.spike_core.cli --output modular-design.json --quiet import "C:\Users\yawar\Documents\Github\TEST\MODULAR-BUS-NIB\MODULAR-BUS-NIB.kicad_pcb"
python -m python.spike_core.cli inspect modular-design.json
python -m python.spike_core.cli inspect modular-design.json --section stackup
python -m python.spike_core.cli inspect modular-design.json --section nets
python -m python.spike_core.cli validate modular-design.json
```

## 2. Prepare A DCIR Request

This creates a request without running the solver.

```powershell
python -m python.spike_core.cli --output modular-12v-dcir-request.json --quiet setup-dc modular-design.json `
  --net "/12Vout" `
  --source "160.132,81.660,F.Cu,12" `
  --load "165.025,78.200,F.Cu,3.333333333" `
  --load "165.025,82.275,F.Cu,3.333333333" `
  --load "165.025,86.350,F.Cu,3.333333334" `
  --mesh-size-mm 0.5 `
  --zone-cell-mm 0.5 `
  --max-conductors 50000 `
  --via-model extracted `
  --via-plating-mm 0.025 `
  --max-drop-mv 50 `
  --max-density 100
```

`--via-model extracted` uses each via's actual start/end layers, drill, and
available plating data. `plated_cylinder` uses the specified plating thickness
for every via while retaining the imported drill and layer span.

## 3. Preflight And Preview

```powershell
python -m python.spike_core.cli preflight modular-12v-dcir-request.json
python -m python.spike_core.cli --output modular-12v-mesh.json --quiet mesh-preview modular-12v-dcir-request.json
```

`preflight` prints a compact readiness and mesh summary. Add
`--include-cells` only when the full cell geometry is needed inline; normally
write it with `mesh-preview`. Do not run a request when preflight reports
`can_solve: false`.

## 4. Run And Report

```powershell
python -m python.spike_core.cli --output modular-12v-dcir-result.json --quiet run modular-12v-dcir-request.json
python -m python.spike_core.cli report modular-12v-dcir-result.json --report-format html --report-output modular-12v-dcir-report.html
python -m python.spike_core.cli report modular-12v-dcir-result.json --report-format csv --report-output modular-12v-dcir-fields.csv
```

The JSON result contains absolute node voltage, source-relative voltage drop,
branch current, current density, copper loss, probe values, warnings, solver
mesh, and provenance.

## 5. Prepare And Run AC R/L Extraction

```powershell
python -m python.spike_core.cli --output modular-vinf-ac-request.json --quiet setup-ac modular-design.json `
  --net "/Vin_f" `
  --source "118.995,66.835,F.Cu,J1" `
  --load "121.3954,66.4972,F.Cu,F1" `
  --start-hz 1000 `
  --stop-hz 30000000 `
  --points 9 `
  --mesh-size-mm 2 `
  --zone-cell-mm 2 `
  --memory-limit-gb 2 `
  --via-model extracted `
  --via-plating-mm 0.025 `
  --skin-effect

python -m python.spike_core.cli preflight modular-vinf-ac-request.json
python -m python.spike_core.cli --output modular-vinf-ac-result.json --quiet run modular-vinf-ac-request.json
python -m python.spike_core.cli report modular-vinf-ac-result.json --report-format html --report-output modular-vinf-ac-report.html
```

The current AC solver returns series resistance, partial inductance,
single-reference approximate capacitance and dielectric conductance, complex
impedance versus frequency, branch current at the final frequency, warnings,
mesh provenance, and RAM-derived branch-admission provenance. It does not yet
solve arbitrary-geometry/multiconductor capacitance, proximity effect, via and
antipad capacitance, or validated multiport PDN impedance.

## Other Commands

```powershell
python -m python.spike_core.cli solvers
python -m python.spike_core.cli benchmark
python -m python.spike_core.cli extract-net modular-design.json --net "/12Vout"
python -m python.spike_core.cli compare baseline.json candidate.json --tolerance-percent 2
python -m python.spike_core.cli run batch-manifest.json --continue-on-error
```
