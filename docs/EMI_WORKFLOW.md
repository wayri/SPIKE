# EMI Test Workbench

## Purpose

The EMI tab owns electromagnetic-interference setup, deterministic pre-pass
screening, external field-solver preparation, and result review. It is separate
from PI and SI because its domain, excitation, boundary, mesh, solver, and
validation requirements are different.

The current release implements setup, preflight, risk screening, persistence,
CLI execution, report traceability, and inspectable openEMS case preparation.
It does not claim near-field, far-field, radiated-emissions, conducted-emissions,
antenna, or compliance results.

## Workflow

```mermaid
flowchart LR
    A["Select candidate and return nets"] --> B["Attach PI, transient, SPICE, or measured metrics"]
    B --> C["Run EMI preflight"]
    C --> D["Rank nets for engineering review"]
    C --> E["Define explicit field ports and domain"]
    E --> F["Prepare inspectable openEMS case"]
    F --> G["Run compatible field solver"]
    G --> H["Import normalized field result"]
    H --> I["Correlate fixtures and review limits"]
```

The first four stages are available. Case preparation is available when design,
stackup, geometry, frequency, mesh, and port checks pass. Solver execution and
field review remain gated by the selected adapter's machine-readable capability
and validation status.

## Contracts

### `spike/emi-setup/v1`

The setup contains:

- candidate/aggressor nets and explicit return/reference nets;
- requested screening, near-field, and far-field stages;
- frequency sweep and test environment;
- mesh resolution, boundary padding, and runtime limit;
- PI/transient/SPICE/measured pre-pass metrics for each candidate net;
- explicit conductor-to-conductor ports when a field case is requested;
- viewport translucency and analysis-net visibility preferences.

Metric magnitudes are inputs with an explicit `source`. SPIKE does not infer a
missing waveform, loop area, return discontinuity, or device model.

### `spike/emi-preflight/v1`

Preflight returns independent `can_screen`, `can_prepare`, and `can_run` gates,
staged readiness, geometry coverage, solver recommendation, and structured
issues. A passing preflight proves setup consistency only. It does not establish
field-solver accuracy or regulatory compliance.

### `spike/emi-workflow/v1`

The current workflow result contains the preflight record and a deterministic
risk ranking. Its provenance states that no field solver was executed and no
compliance prediction was produced.

## Desktop Process

1. Open **EMI - Net domain** and select candidate and return nets. Hovering a net
   cross-highlights its board geometry.
2. Open **EMI - Preflight** and provide defensible `dV/dt`, `dI/dt`, peak current,
   loop area, and return-discontinuity metrics. Record whether they came from a
   SPIKE result, SPICE, measurement, or a reviewed manual estimate.
3. Run **Risk screen**. The dashboard ranks selected nets and lists traceable
   reasons and mapped tracks, vias, zones, layers, and routed length.
4. Open **EMI - Ports** for full-wave preparation. Define finite 3D start/stop
   points, direction, impedance, and exactly one excited port for the current
   openEMS single-excitation adapter.
5. Open **EMI - Domain mesh** and set frequency, free-space boundary padding,
   resolution, and runtime bound. Prepare the case and inspect all warnings.
6. Use **EMI - Dashboard** and the engineering report to review readiness and
   preserve the screening and capability record.

The project stores setup, preflight, and screening records under the top-level
`emi` member. Save and reopen round-trips the records without promoting their
model status.

## CLI

```text
spike --output emi-preflight.json emi-preflight board.kicad_pcb emi-setup.json
spike --output emi-screening.json emi-screen board.kicad_pcb emi-setup.json
```

Both commands accept a KiCad board, DesignIR JSON, or SPIKE project as the design
argument. Screening exits successfully only when the setup has complete,
non-zero electrical pre-pass metrics and mapped conductor geometry.

## Accuracy And Release Gates

Before near-field, far-field, or compliance controls can be enabled, SPIKE needs:

- a fixed, process-isolated adapter and normalized field-result contract;
- complete material, conductor, via, port, and boundary export;
- mesh-convergence and passivity/energy checks where applicable;
- analytical and canonical electromagnetic fixtures;
- correlation against an independent trusted solver;
- measured near-field and chamber data with documented fixtures;
- applicability limits, expected error, known failures, and non-certification
  language in every report;
- reviewed redistribution, dependency, SBOM, and license obligations.

An EMI screen identifies where to investigate. It is not a pre-compliance test.

