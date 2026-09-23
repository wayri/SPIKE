# Power Tree Capability Benchmark

## Objective

SPIKE's power tree is the system-level preparation surface for PI analysis. It must connect design intent, operating scenarios, PCB geometry, circuit models, and solver results in one traceable graph.

## Reference Capability Class

Siemens describes HyperLynx PI as a progressive workflow spanning DC drop, AC decoupling, PDN optimization, and power-aware SI. Xpedition supplies the integrated schematic, layout, analysis, and data-management context. Analog Devices LTpowerPlanner demonstrates the expected system power-tree interaction: source-to-load diagrams, multiple outputs and loads, voltage/current/efficiency parameters, total power/loss/efficiency, architecture comparison, and linked detailed models.

SPIKE will use those capabilities as requirements, not as a claim of present equivalence.

## Delivery Gates

### Gate A: Topology and budget

- Extract candidate rails and connected functional blocks.
- Edit sources, converters, loads, series/shunt devices, connectors, and harnesses.
- Assign operating values, limits, and model references.
- Calculate scenario power, loss, efficiency, and overload warnings.
- Persist the graph and pass it through the versioned solver contract.
- Persist named operating scenarios and per-load current, power, and inclusion overrides.
- Provide linked diagram, component-consumption, and rail-job views.
- Generate explicit single-rail or batch PI jobs with real pad anchors where references resolve.

Implemented in the current development build. The remaining Gate A gap is high-confidence hierarchical schematic interpretation for arbitrary converter symbols and automatic pin-role inference.

### Gate B: Geometry-resolved DC

- Map each graph edge to routed traces, pads, zones, vias, and connector pins.
- Validate terminals, connectivity, material data, and mesh convergence.
- Overlay solved voltage, current density, and loss on the graph and PCB.

### Gate C: AC PDN

- Attach VRM and capacitor impedance models.
- Sweep self/transfer impedance with target overlays.
- Detect resonances and compare capacitor alternatives.
- Publish frequency validity and approximation warnings.

### Gate D: System and power-aware SI

- Include harnesses, connectors, and multiple boards.
- Feed supply-noise results into channel and eye analysis.
- Compare revisions and operating scenarios with reproducible reports.

## Truth Policy

Topology budgets, circuit simulation, 2.5D extraction, and full-wave solving are distinct capabilities. SPIKE reports the active method, assumptions, solver identity, validation state, and failure modes. A fast budget estimate must never be labeled as a DC field solution.

PTree is used only as a public workflow reference for source/load diagrams, consumption tables, and project statistics. Its GPL-3.0 implementation is not copied into SPIKE. HyperLynx is used as the capability benchmark for progressive DC, AC/decoupling, PDN optimization, and power-aware analysis; SPIKE does not claim present equivalence.
