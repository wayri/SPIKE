# PEEC and ngspice Hybrid Execution

## Implemented path

SPIKE can execute a reviewed one-way hybrid analysis:

1. `spike.peec_2_5d` extracts one or more `spike/rlgc-network/v1` records.
2. `list_peec_spice_networks` exposes the extraction mesh endpoints and asks the
   user to map each selected network to explicit circuit nodes.
3. `import_peec_rlcg` appends the selected equivalent R/L/C/G section to a
   `spike/spice-workspace/v1` project only when the extraction has completed
   without error issues and `endpoint_reviewed=true`.
4. The SPICE workspace composes assigned component/subcircuit models and the
   reviewed parasitic sections into a deterministic self-contained netlist.
5. `run_hybrid_cosimulation` runs that netlist through the process-isolated
   ngspice adapter and returns waveforms, visualization bindings, stress data,
   issues, and combined provenance.

The same operations are available through the CLI:

```text
spike peec-spice-import extraction.json workspace.json mappings.json
spike hybrid-run board.kicad_pcb extraction.json workspace.json mappings.json
```

`mappings.json` is an array. Each entry contains `network_index`, `from_node`,
`to_node`, `reference_node` when C/G is present, and
`endpoint_reviewed: true`.

## Electrical representation

The current importer creates a series R/L section with a sink-side shunt C/G
to the explicit reference node. It uses only the scalar equivalent values
published by the PEEC result. It does not silently fit the frequency-dependent
Z(f) sweep, infer circuit nodes from coordinates, or modify the extracted
copper model.

This representation is suitable for traceable circuit studies whose required
accuracy is compatible with the source extraction status. It is not a general
wideband macromodel.

Failed, unsupported, incomplete, or error-bearing extraction results cannot
be catalogued or imported even when they retain partial network data. Rerun
the extraction successfully before mapping its endpoints.

## Validity boundary

The workflow is **staged one-way coupling**, not an iterative closed-loop
field/circuit solve. Device currents do not currently cause the field solver to
re-extract a state-dependent geometry model. The combined result cannot have a
stronger model status than its weakest extraction or circuit input.

A production closed-loop workflow still requires:

- a multiconductor electrostatic C/G matrix including pads, vias, antipads,
  dielectric dispersion, and explicit returns;
- a passive, causal wideband network reduction or direct field/circuit
  coupling contract;
- bounded iteration controls and convergence evidence;
- nonlinear/model-library validation and reviewed pin-to-geometry mapping;
- correlation against analytical, independent-solver, and measured fixtures.

## Security and reproducibility

ngspice runs out of process with bounded time and output. The generated netlist
rejects shell, include, library, control, and other unsafe directives. Model and
endpoint intent remains in the project workspace; the generated netlist is a
preview artifact, not an editable source of truth.
