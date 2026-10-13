# ADR 0075: Board-bound Studio handoff and coupled feedback

Status: implemented for development; numerical release review required.

## Context

Advanced circuit setup needs PCB selection and placement context. A board does
not provide device compact models, thermal parameters or valid operating ranges.
Standalone SPIKES Studio already owns a circuit document/editor. The desktop
worker already isolates native electrical execution and thermal orchestration.

## Decision

Keep the browser drawing inert: exact board part/pin/net identities and placement,
with copper-guided display wires and labels. Executable devices require explicit
reviewed model and pin bindings. Handoff uses a bounded versioned JSON graph,
fixed local staging and a fixed first-party launcher. Missing optional Studio
runtime is an inspectable unavailable state, not worker startup failure.

Keep numerical feedback in the worker using native electrical sessions and the
existing lumped thermal kernel. Correlate accepted progress to the worker ID;
retain source revision, model inputs, native library hash and residuals. Native
checkpoints roll back trials; only converged windows enter plots. The host owns
cancellation. File-bound project APIs are not used for supplied neutral data.

Geometry feedback initially updates explicitly supplied uniform conductor
parameters, with nominal resistance agreement and bounded temperature validity.
No model is inferred from BoM values or copper artwork. Nonlinear devices,
spatial thermal fields, airflow and structural deformation retain their existing
separate admission/evidence requirements.

## Consequences

The native Studio and browser workbench share reviewed board intent without
embedding wxPython in the renderer or adding numerical domain logic to Rust.
The optional Studio source runtime must be separately packaged before installed
launch can be claimed. Human numerical review and case-specific step refinement
remain required before release/use for qualified engineering conclusions.

See [board workflow](../SPIKES_BOARD_STUDIO.md) and
[coupling contract/evidence](../STUDIO_BOARD_COSIMULATION.md).
