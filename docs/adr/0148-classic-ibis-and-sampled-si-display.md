# ADR 0148: Classic IBIS execution and sampled SI display

Date: 2026-10-25. Status: accepted for experimental source implementation;
numerical human review and release qualification remain open.

## Decision

Keep the loaded linear SI endpoint reduction unchanged. Add a separate inert
compiler for a strict classic IBIS subset, followed by explicit trusted native
ngspice execution under the existing process supervisor. No raw-netlist IPC
execution route, AMI runtime, automatic download, memory-policy relaxation or
unsupervised retry is introduced. Retain source hashes, selected corners,
calibration diagnostics, generated deck hash and returned runtime provenance.

Keep spatial display separate from categorical aggressor/victim route colors.
Admit a bounded complex sampled-data contract against the current worker-derived
canonical design digest, board occurrence, two canonical net IDs and request ID.
Derive trace sample positions from authoritative segment fractions; retain field
XYZ directly. A supplied uniform coupled-line run may map its actual returned
victim-voltage probes to an explicitly assigned straight pair. It must preserve
its supplied-RLGC status and cannot produce surrounding E-field samples.

## Consequences

The UI provides three IBIS steps and sampled SI controls in existing panels,
with display in the main single-board 3D viewport. Imported source authenticity
is not established by a matching self-declared digest. Neither a spatial color
map nor a successful engine launch promotes a solver/model to qualification.
Unsupported model keywords and geometry fail closed. Session-only drafts require
explicit exports; transformed multi-board overlays and automatic persistence
remain future work.

The [independent method](../validation/IBIS_DRIVER_RECEIVER_DERIVATION_20261025.md),
[user/API guide](../SI_IBIS_SPATIAL_WORKFLOW.md) and
[finite closure campaign](../MATURITY_CLOSURE_20261025.md) define scope and gates.
