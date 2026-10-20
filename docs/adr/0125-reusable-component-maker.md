# ADR 0125: inert component packages and explicit build paths

Status: accepted for engineering-preview source implementation.

## Context

Symbol editing, model intake, sampled controllers and HDL tools need a unified
component editor and reusable circuit capture without executing imported code
or silently changing model semantics.

## Decision

Use `spikes/component-package/v1` and `.spkcmp` for identity/version, ordered
symbol terminals, geometry, implementation source and provenance. Loading is
inert. The user store rejects same-version changes. Implementation/pin digests
bind explicit compilation consent. Outputs use content-addressed owned children;
unrelated or modified files fail closed. Trust is not hostile-code isolation.

Separate SPICE packaging/preflight, sampled C++ controller compilation and
Verilog compilation. Do not claim a continuous C++ device ABI or analog/HDL
coupling. SPICE insertion uses the existing parser on a clone before a single
undo commit. Unknown source is preservable but not silently executable. Custom
primitive symbols retain pin identity. Subcircuits display through checked
compact projections; native flattened primitives and source remain authoritative.
All native endpoints on a public node map to its public anchor, while internal
wires stay inside the hierarchy. Unsafe/stale mappings reveal the flattened
view rather than invent connections. `reusable_block_projection.py` owns this
presentation, selection expansion and undoable transforms.

Capture selections/subsheet definitions without modifying the source circuit.
Retain ports, dependencies and supported parameter specialization; reject
non-reproducible nested/scoped cases. No new numerical equations are introduced.

## Ownership and checks

`component_package.py` owns schema/store/insertion; `component_capture.py` owns
capture; `component_build.py` owns consent-gated compilation;
`component_maker.py` owns the wx editor. Existing renderers and commands consume
these services. See the [workflow](../../standalone/spikes_project/studio/docs/COMPONENT_MAKER.md).

Checks cover version/pin/undo rejection, native RC waveform equivalence,
parameter-shadowing counterexamples, actual C++/Icarus compilers, hash-bound
approval and native wx workflows. No physics qualification follows from them.
Executed checks and limitations are retained in the
[verification record](../validation/SPIKES_COMPONENT_MAKER_VALIDATION.md).
