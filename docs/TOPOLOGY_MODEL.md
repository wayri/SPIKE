# SPIKE Topology Model

## Purpose

`spike/topology/v1` represents the engineering topology used to prepare PI and SI/HF analyses. It is independent of the rendered PCB and of any specific solver implementation.

The model supports:

- Automatic extraction from a parsed PCB netlist.
- KiCad schematic symbol cross-reference using `.kicad_sch`.
- KiCad XML netlist ingestion.
- User-created and user-edited elements and connections.
- Typed multi-port blocks with exact edge endpoints, connection limits, lane and
  differential-pair annotations.
- Separate PI power-distribution and SI/HF channel graphs.
- A synchronized deterministic text equivalent for accessibility, review, and
  source-control diffs.
- Persistence inside the SPIKE project package.
- Inclusion in the versioned solver request.
- Operating-case power budgets with per-stage voltage, current, loss, efficiency, and limit checks.

## Contract

```json
{
  "contract": "spike/topology/v1",
  "domain": "pi",
  "name": "Power distribution tree",
  "scenarios": [
    { "id": "typical", "label": "Typical", "loadMultiplier": 1.0 },
    { "id": "maximum", "label": "Maximum", "loadMultiplier": 1.25 }
  ],
  "nodes": [
    {
      "id": "pi-net-24v",
      "kind": "rail",
      "label": "24V",
      "net": "24V",
      "voltageV": 24,
      "maxCurrentA": 8,
      "x": 274,
      "y": 35,
      "origin": "extracted"
    }
  ],
  "edges": [
    {
      "id": "source-24v",
      "from": "source-1",
      "to": "pi-net-24v",
      "net": "24V",
      "kind": "power",
      "origin": "user"
    }
  ],
  "extraction": {
    "source": "board_netlist",
    "generatedAt": "2026-07-27T00:00:00.000Z",
    "warnings": []
  }
}
```

## Multi-port blocks

`ports` is an additive `spike/topology/v1` field. Existing node-only edges
remain readable. New connections bind both endpoints explicitly:

```json
{
  "nodes": [
    {
      "id": "channel-1",
      "kind": "channel",
      "label": "PCIe lane 0",
      "ports": [
        { "id": "in_p", "label": "IN+", "direction": "input", "kind": "signal", "side": "left", "pair": "lane0", "lane": "lane0", "maximumConnections": 1 },
        { "id": "in_n", "label": "IN-", "direction": "input", "kind": "signal", "side": "left", "pair": "lane0", "lane": "lane0", "maximumConnections": 1 },
        { "id": "out_p", "label": "OUT+", "direction": "output", "kind": "signal", "side": "right", "pair": "lane0", "lane": "lane0", "maximumConnections": 1 },
        { "id": "out_n", "label": "OUT-", "direction": "output", "kind": "signal", "side": "right", "pair": "lane0", "lane": "lane0", "maximumConnections": 1 }
      ]
    }
  ],
  "edges": [
    {
      "id": "driver-p-to-channel-p",
      "from": "driver-1",
      "fromPort": "out_p",
      "to": "channel-1",
      "toPort": "in_p",
      "portBinding": "explicit",
      "kind": "signal",
      "net": "PCIE_TX0_P",
      "origin": "user"
    }
  ]
}
```

Port direction is `input`, `output`, `bidirectional`, `passive`, `reference`,
or `control`. Electrical kind is `power`, `return`, `signal`, `reference`,
`control`, or `shield`. Blocks may expose any number of ports; the editor
provides neutral generic templates, a deliberate SI differential template,
and per-port editing. Generic SI blocks do not assume differential signaling.

Legacy edges are assigned reviewable inferred endpoints only when normalized;
`portBinding: inferred` remains visible and is not equivalent to a reviewed
solver terminal. Explicit wiring records `portBinding: explicit`. The shared
validator rejects missing endpoint ports, half-bound edges, invalid direction,
duplicate endpoint pairs, self-loops, and exceeded connection limits.

## Text equivalent

The Diagram/Text switch produces `SPIKE TOPOLOGY TEXT v1`. It contains the
domain, name, extraction source, scenarios, nodes, electrical/model properties,
ports, connections, binding state, and warnings. Ordering and JSON escaping are
deterministic, non-finite numbers are rejected, and canvas coordinates are
excluded so moving a block does not create a semantic diff.

The text representation is deliberately read-only. It can be copied or
exported as `.spike-topology.txt` for reviews and accessibility. Canonical JSON
can be copied separately for machine round-trip; the text form is not imported
and cannot become a competing topology source.

## PI Elements

- `source`: supply, battery, adapter, or upstream board.
- `regulator`: buck, boost, LDO, PMIC, or other conversion stage.
- `rail`: named PCB power or return net.
- `connector`: board connector or terminal block.
- `harness`: cable or interconnect segment.
- `load`: IC, motor, module, or downstream consumer.
- `passive`: resistor, capacitor, inductor, ferrite, diode, or protection element.

## SI/HF Elements

- `driver`
- `channel`
- `connector`
- `harness`
- `termination`
- `receiver`

## Extraction Policy

Board extraction uses pad-to-net membership as the connectivity authority. Component references and values classify elements. Power and high-speed net naming heuristics reduce the initial graph to relevant nets.

A `.kicad_sch` file currently improves component identity while the PCB netlist remains the routed-connectivity authority. This avoids claiming connectivity that cannot be resolved safely from schematic coordinates alone.

KiCad XML netlists provide explicit component-to-net connectivity and can be used without a PCB. Geometry-dependent analysis still requires a board design source.

All inference warnings are retained in `extraction.warnings`. Users must resolve missing sources, drivers, loads, and receivers before the relevant solver may run.

## Solver Handoff

PI analysis requests include the graph at:

```text
spec.options.topology
```

Before request creation, SPIKE verifies:

- The PI graph contains a source.
- The PI graph contains a load.
- Every edge references existing nodes.
- The selected routed net has explicit source and sink terminals.

Solvers may consume the topology for staging, circuit assembly, model assignment, and reporting. They must continue to use normalized PCB geometry for extracted electrical parameters.

## Power Budget

The desktop workbench performs a deterministic source-to-load budget before solver handoff. Optional node fields are:

- `voltageV`: source, regulator output, or rail voltage.
- `loadCurrentA` / `loadPowerW`: load demand. Explicit power takes precedence.
- `efficiencyPercent`: regulator conversion efficiency.
- `resistanceOhm`: series element, connector, or harness resistance.
- `maxCurrentA`: operating limit used for warnings.
- `enabled`: scenario inclusion switch.
- `modelLink`: reference to a SPICE, behavioral, or library model.

The budget propagates downstream demand upstream, applies regulator efficiency and `I^2R` series loss, and supports typical, maximum, standby, and custom load multipliers. It reports disconnected loads, missing values, overloads, cycles, and multi-parent paths.

Loads can override the baseline demand per persisted operating case:

```json
{
  "kind": "load",
  "loadCurrentA": 1.5,
  "operatingPoints": {
    "standby": { "currentA": 0.03 },
    "maximum": { "currentA": 2.2 },
    "shipping": { "enabled": false }
  }
}
```

Scenario values are absolute. A scenario multiplier applies only when a load has no explicit current or power for that case. This prevents maximum-case values from being multiplied twice.

## Power Tree Analysis Plan

`buildPowerTreeAnalysisPlan()` converts the selected operating case into `spike/power-tree-analysis-plan/v1`. The plan contains one geometry-analysis job per routed rail, its nearest source or conversion-stage blocks, its same-rail loads, voltage/current demand, and actionable setup warnings.

The desktop app maps component references to real pads on the rail and preserves each pad's connected copper-layer span. Jobs with missing physical anchors remain visible for manual placement; SPIKE does not silently select unrelated pads. Multiple rails are handed to the existing PI batch workflow.

The workbench provides three linked views:

1. Source-to-load block diagram with explicit series, shunt, return, and isolation intent.
2. Per-component consumption table for each operating case.
3. Rail job summary showing voltage, current, power, loads, terminals, and readiness.

Rows and graph blocks cross-highlight the corresponding PCB component or net.

This calculation is a topology-level estimate. It is not a replacement for geometry-resolved DC drop, AC impedance, decoupling optimization, or electromagnetic field solving.

## Product Benchmark

The workflow is benchmarked against the capability class represented by Siemens HyperLynx/Xpedition and system power planners, without copying proprietary presentation or implementation:

1. Left-to-right source, conversion, distribution, and load hierarchy.
2. Schematic/netlist extraction with editable engineering intent.
3. Multiple outputs, loads, connectors, harnesses, and shunt elements.
4. Operating scenarios, current limits, power loss, and efficiency.
5. Model assignment and a stable handoff to DC, AC, SPICE, 2.5D, and 3D solver plugins.
6. Progressive verification: budget, geometry validation, DC solve, AC/PDN solve, and power-aware SI.
7. Architecture comparison and automated decoupling alternatives in a later validated phase.

## Current Limits

- Automatic regulator input/output direction is heuristic.
- Hierarchical schematic connectivity is not independently reconstructed yet.
- Pin-level SPICE and IBIS assignments are not part of `v1`.
- Parallel-source current sharing and cyclic/meshed power networks require a circuit solver; the budget flags them.
- Architecture comparison and automatic capacitor optimization are not yet implemented.
- A ready analysis plan prepares geometry-resolved DC jobs; it is not itself a DC field solution.
- SI/HF topology now retains editable ports and exact endpoint connections, but
  model-bound run-plan compilation and validated channel solvers remain
  capability-gated.
- Harness and connector elements are structural until their electrical models are assigned.
