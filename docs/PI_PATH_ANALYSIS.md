# Ordered PI Path Analysis

SPIKE represents an end-to-end power path as ordered copper meshes separated by
explicit component interfaces. A PCB net is never treated as if it continued
through a package by itself.

## Contract

`spike/pi-path/v1` contains:

- `source_terminal`: the first net and reviewed source pad;
- `segments`: ordered copper nets from input to output;
- `transitions`: one component interface between every adjacent pair of nets;
- `load_terminal`: the last net and reviewed load pad.

Each transition identifies the component, input pad, output pad, equivalent
model, and solver policy. The worker rejects unknown pads, incorrect pad/net
mappings, missing transitions, or ambiguous ordering through
`validate_pi_path` before solving.

## Desktop workflow

1. Open **PI > Power paths** and extract a path between explicit source and
   load pads, or draw and review the path manually.
2. Assign input/output pads and an equivalent model to every series component.
3. Choose **Use for analysis**. The PI setup selects the path, anchors its
   source on the first net, and anchors its sink on the last net.
4. Review the ordered chain in **Analysis path** and run the compatible engine.
5. Open **PI > SPICE models** for nonlinear or time/frequency-dependent parts.

## Execution boundary

The hybrid DC solver executes reviewed linear resistance interfaces today. It
stamps each interface between the two adjacent conductor meshes and reports its
current, voltage drop, resistance, and power loss separately from copper loss.
This supports resistors and explicitly linearized operating-point resistance
for a device when that approximation is deliberately supplied and reviewed.

Inductors, capacitors, MOSFETs, regulators, transformers, behavioral models,
AC interfaces, and transient interfaces are not silently reduced to DC
resistors. They must use the SPICE workspace and the staged PEEC-to-ngspice
workflow described in `SPICE_WORKSPACE.md` and `PEEC_NGSPICE_HYBRID.md`.
Closed-loop iterative field/circuit execution remains a release gate.

## Verification

`tests/python/test_pi_path.py` covers contract validation, wrong-net rejection,
worker exposure, and a two-net 1 A solve through a 100 mOhm series component.
`app/scripts/test-power-tree.mjs` verifies that board extraction compiles the
source pad, ordered nets, component pin mapping, and load pad without flattening
the path into independent net jobs.
