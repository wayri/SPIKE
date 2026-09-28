# EM Test Workbench

## Purpose

The EM tab owns electromagnetic-interference setup, deterministic pre-pass
screening, external field-solver preparation, and result review. It is separate
from PI and SI because its domain, excitation, boundary, mesh, solver, and
validation requirements are different.

The current release implements setup, preflight, risk screening, persistence,
CLI execution, report traceability, and inspectable openEMS case preparation.
An admitted external engine may produce bounded field or NF2FF results, but the
core risk screen does not calculate fields, and neither path establishes a
calibrated radiated- or conducted-emissions compliance result.

For an executed, bounded **virtual** review that pairs this screen with the
optional EMerge extension's relative radiation pattern and the EM chamber
overlay, follow the [EM + EMerge tutorial](VIRTUAL_EMI_EMERGE_TUTORIAL.md).
That separate EMerge solve does not promote the core EMI screen to a calibrated
emissions or compliance result.

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

1. Open **EM - Net domain** and select candidate and return nets. Hovering a net
   cross-highlights its board geometry.
2. Open **EM - Preflight** and provide defensible `dV/dt`, `dI/dt`, peak current,
   loop area, and return-discontinuity metrics. Record whether they came from a
   SPIKE result, SPICE, measurement, or a reviewed manual estimate.
3. Run **Risk screen**. The dashboard ranks selected nets and lists traceable
   reasons and mapped tracks, vias, zones, layers, and routed length.
4. Open **EM - Ports** for full-wave preparation. Define finite 3D start/stop
   points, direction, impedance, and exactly one excited port for the current
   openEMS single-excitation adapter.
5. Open **EM - Domain mesh** and set frequency, free-space boundary padding,
   resolution, and runtime bound. Prepare the case and inspect all warnings.
6. Use **EM - Dashboard** and the engineering report to review readiness and
   preserve the screening and capability record.

The project stores setup, preflight, and screening records under the top-level
`emi` member. Save and reopen round-trips the records without promoting their
model status.

## Radiated-emissions reference profiles

In **EM - Net domain**, the optional reference selector records an exact
edition and class or platform in `radiated_emissions_standard`. Existing setups
without a selection remain valid. These are *reference labels*, not limit
curves or compliance presets:

| Selection | Scope | Required selection |
| --- | --- | --- |
| [CISPR 32:2015+AMD1:2019](https://webstore.iec.ch/en/publication/65836) | Multimedia equipment | Class A or B |
| [CISPR 25:2021](https://webstore.iec.ch/en/publication/64645) | Automotive/on-board receiver protection | Class 1, 2, 3, 4, or 5; applicability requires review of the controlled standard text |
| [MIL-STD-461H:2026 RE102](https://quicksearch.dla.mil/qsDocDetails.aspx?ident_number=35789) | Current military electric-field radiated-emissions method | Platform category; detailed applicability requires review |
| [MIL-STD-461G:2015 RE102](https://quicksearch.dla.mil/qsDocDetails.aspx?ident_number=35789) | Historical revision, only for an explicitly G-bound program | Platform category; G limits must not be used as H limits |

CISPR 25 does **not** use the CISPR 32 A/B selector. “MIL-431” has not been
identified as an RE method and is rejected rather than silently interpreted as
MIL-STD-461. The selected reference and source travel with the preflight result.
Unknown editions, mismatched classes/platforms, and embedded numeric limit
claims are rejected with structured `EMI_STANDARD_*` issues.

No numeric limit tables are bundled. IEC publication content cannot be
redistributed merely because a catalog page is public; see the
[IEC copyright policy](https://webstore.iec.ch/copyright). The field adapter
also lacks qualified detector, measurement bandwidth, receiving antenna,
polarization, fixture/distance, and measured-correlation evidence. Thus
`comparison_status` remains `unavailable`, `compliance_available` is `false`,
and selecting a standard cannot change the solver-readiness gate or produce a
pass/fail claim. NF2FF magnitude or the EMerge relative pattern is not a
CISPR/MIL receiver reading. A future comparator requires reviewed rights for
limit data, exact edition/conditions, calibrated measurement or validated
equivalent, and independent correlation before any compliance claim.

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
