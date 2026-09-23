# SPICE Workspace

SPIKE stores circuit intent in `spike/spice-workspace/v1`. The workspace is
shared by PI and SI and is persisted inside the `.spike` project package. It is
not an ngspice input file. The worker validates it and composes a deterministic
netlist preview before any solver is invoked.

## Ownership

- `app/src/spiceWorkspace.ts` owns frontend types, defaults, board-pad helpers,
  and explicit import of parasitic results.
- `app/src/SpiceWorkbench.tsx` edits models, component assignments, pin/pad
  bindings, parasitic endpoints, and operating-point/AC/transient setup.
- `python/spike_core/spice_workspace.py` is the validation and deterministic
  composition boundary.
- `python/spike_core/ngspice_plugin.py` owns process-isolated ngspice execution.
- `schemas/spice-workspace-v1.schema.json` is the portable wire contract.

## Required Workflow

1. Select PI or SI as the workspace domain.
2. Add a built-in primitive or an explicitly stored subcircuit.
3. Assign the model to a DesignIR component and map every model pin to a board
   pad and circuit node.
4. Import geometry parasitics only from a traceable solver result.
5. Review and confirm every imported parasitic endpoint. Generated `:source`
   and `:load` placeholders are never accepted silently.
6. Select an explicit ground/return node and analysis setup.
7. Validate, inspect the generated netlist, then invoke ngspice.

## Safety Boundary

The composer does not search the filesystem or expand `.include` directives.
Inline model source is bounded to 2 MiB and rejects process, file, control,
analysis, and other worker-owned directives. Primitive expressions are bounded
and single-line. IDs, pins, counts, transient step budgets, references, and
pad mappings are validated before composition.

This boundary reduces accidental or unreviewed execution; it is not yet a full
SPICE parser or a signed model library. Imported vendor models still require a
future immutable content-addressed quarantine/approval store before SPIKE can
claim a production-grade model supply chain.

## Current Validity

The workspace and deterministic composition are operational. A real ngspice
RC transient smoke has passed. Geometry-derived parasitics retain the validity
status supplied by their source solver. Stable multi-terminal PEEC extraction,
validated device libraries, complete stress mapping, and closed-loop PI/SI
correlation remain release gates.

## PI power-path entry

The PI ribbon and PI setup both expose **SPICE models** directly. Ordered
multi-net PI paths use `spike/pi-path/v1`; their source and load may be on
different nets, and every intervening package has reviewed input/output pad
mapping. Linear DC resistance interfaces execute in the conductor solver.
Reactive, nonlinear, behavioral, AC, and transient interfaces open this
workspace for explicit model assignment and staged PEEC/ngspice execution.
