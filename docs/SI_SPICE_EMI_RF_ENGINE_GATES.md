# SI, SPICE, EMI, And RF Engine Gates

## Rule

UI controls and schemas may be prepared before a solver is available, but SPIKE
must not present a numerical capability as implemented until its engine,
validation fixtures, applicability limits, and redistribution license have all
passed review.

## Planned Execution Chain

```text
DesignIR
  -> complete-net and coupled-net geometry
  -> stackup/material model
  -> quasi-static RLC extraction
  -> frequency-validity gate
  -> circuit network
  -> SPICE or behavioral co-simulation
  -> waveforms, S-parameters, TDR/TDT, and eye analysis
  -> warnings and validation report
```

The geometry contract must include routing, filled zones, pads, via spans,
reference conductors, dielectric thickness, permittivity, and loss tangent.
Protocol presets only configure limits and stimulus. They do not replace IBIS,
SPICE, package, connector, or interconnect models.

SPIKE now implements those presets through the declarative
`spike/si-protocol-suite/v1` contract and the SI Protocol Suites workbench.
Dedicated setup profiles cover DDR/LPDDR, GDDR, HBM, generic SerDes, LVDS,
PCI, PCIe, PXI, PXI Express, DisplayPort, HDMI, USB, Ethernet, MIPI, SATA,
CXL, and JESD204. Users can create additional suites through equivalent GUI
and JSON-code builder modes. Suite availability means configuration is
available; it does not mean the shared SI engines or protocol compliance are
validated.

Normative standards tables, masks, and clauses may be licensed or
revision-specific. Built-in suites therefore contain workflow structure and
public provenance only. An authorized user must supply reviewed limits and
retain their source/clauses. A protocol PASS is forbidden until the active
licensed revision, models, de-embedding policy, numerical validation, fixture
uncertainty, and applicable compliance procedure are all bound to the result.

All execution uses the versioned plugin boundary described in
`SOLVER_PLUGIN_ARCHITECTURE.md`. The current catalog reserves
`spike.peec_2_5d`, `spike.mom_surface`, `spike.fullwave_3d`, and
`spike.ngspice`; a reserved ID is not a claim that the engine is available.

## Capability Gates

| Capability | Required before release |
| --- | --- |
| Broadband PI | Validated frequency-dependent RLC extraction, decoupling ESR/ESL models, convergence and frequency-limit warnings |
| SI / NEXT / FEXT | Coupled-line fixtures, reference-plane and return-path model, trusted comparison results |
| NRZ eye | Validated channel network, driver/receiver or IBIS models, jitter/noise provenance |
| PAM4 eye | Multilevel stimulus and slicer models, level-dependent noise/jitter fixtures, BER interpretation limits |
| Closed-loop SPICE | Deterministic extracted subcircuits, pinned ngspice interface, model sandbox and timeout policy |
| Behavioral IC blocks | Versioned ABI for C/C++ and Verilog stand-ins, declared timestep/state limits, deterministic tests |
| EMI/EMC | Calibrated radiated/conducted fixtures and explicit non-certification language |
| PCB antenna/full wave | Validated mesh/material/port setup and measurement or trusted-tool correlation |

## Open-Source Engine Review

Candidate engines must be evaluated for numerical suitability, maintenance,
platform support, license obligations, process isolation, and commercial
distribution. Do not embed an engine merely because it is open source.

- Prefer process-level adapters with versioned files or JSON contracts.
- Keep engine-specific meshes and setup out of DesignIR.
- Record engine name, version, options, convergence, and license metadata in
  every result.
- Keep optional engines as separate bundles when their license or footprint
  makes inclusion in the commercial desktop installer inappropriate.
- Never allow a solver subprocess to receive arbitrary shell strings or access
  paths outside the project, approved libraries, and its job directory.

## Current Status

Complete-net geometry extraction, KiCad stackup import, solver catalog
selection, process isolation, and the optional ngspice batch adapter are
available.
Touchstone S/Z/Y ingestion, conversion, renormalization, mixed-mode traces,
passivity/reciprocity checks, group delay, matched-port impedance, and offline
desktop plotting are available as network post-processing. Separate bounded
geometry paths now accept either one straight constant-width trace or two
straight parallel coextensive traces over one simple covering reference zone.
They create experimental scalar/matrix RLGC, reciprocal two/four-port S,
explicit unwindowed TDR/TDT, and a normalized ideal-source NRZ eye. The paired
path adds sparse 2-D cross-section capacitance and bounded geometry-derived
NEXT/FEXT. This does not admit general PCB coupling, vias, launches, connectors,
return-path discontinuities, or source/receiver geometry and makes no signoff
or protocol-compliance claim. See `GEOMETRY_DERIVED_SI_CHANNEL.md`.
Broadband HF, closed-loop SPICE, behavioral blocks, eye diagrams, PAM4,
EMI/EMC, and full-wave antenna analysis remain `unsupported`, `planned`, or
`research` in the machine-readable capability response except for the bounded
normalized NRZ eye, which is explicitly `experimental` and is not a statistical
or protocol eye.

Public overview sources used to structure, not reproduce, the built-in suites:

- PCI-SIG PCI Express Base overview and revision catalog:
  https://pcisig.com/specification-overview/pci-express-base
- VESA DisplayPort compliance-program overview:
  https://vesa.org/displayport-developer/compliance/
- HDMI specification-access and compliance-program overviews:
  https://www.hdmi.org/spec/index and https://www.hdmi.org/resource/testing

Restricted specifications are not copied into SPIKE. Public names and general
workflow concepts are independently represented; normative content remains a
user-supplied, provenance-bound input.
