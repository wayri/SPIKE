# Multi-board reduced-network orchestration

This boundary records the exact information that a future coupled PI or SI
adapter must consume. It is deliberately a binding/compilation step, not a
field solve and not an analysis result.

`spike/multiboard-coupled-reduced-network-bind-request/v1` accepts a valid
coupled-harness plan and requires all of the following:

- one immutable-digest reduced board model for each selected board, with typed
  connector/pin ports and their signal, return, and optional shield terminals;
- an explicit connector R/L binding for every selected harness endpoint pin;
- explicit per-conductor harness R/L values (with optional C/G only when an
  explicit reference node is named);
- a declared return path with R/L values for every selected harness; and
- declared return references, plus optional shield paths only when both board
  ports declare an explicit shield node and reference.

The emitted `spike/multiboard-coupled-reduced-network-bind-result/v1` carries
the board-model digests, normalized port/connector mapping, and a linear
circuit fragment containing only the supplied connector, signal-conductor,
return, and optional shield elements. Material names, AWG, geometry, layer
names, connector IDs, and visual harness lines never supply an electrical value
by implication.

Optional `mutual_terms` are retained only when the caller identifies both
compiled harness conductors and supplies `mutual_inductance_h`. They are not
executed by this boundary because the present fragment engine lacks a
mutual-inductor/distributed multiconductor primitive. No mutual coupling is
invented from cable length, spacing, shielding, or shared references.

## Qualification boundary

The binding result always reports:

- `production_qualified: false`;
- `solver_executed: false` and `field_coupling_executed: false`; and
- `mutual_terms_executed: false`, even when explicit terms are retained.

Execution remains blocked until a versioned PI reduced-circuit or SI N-port
cascade adapter consumes the exact binding digest; each has explicit
source/load, analysis, reference-plane/de-embedding, cancellation, CPU/RAM,
and result/provenance contracts. Promotion also requires analytical,
independent-solver, and measured two-board harness fixtures. An independent
per-board SI batch does not satisfy any of those coupled-physics gates.
