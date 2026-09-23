# SPIKES qualified model library contract

SPIKES has a fail-closed local index and KiCad-symbol mapping format in
`python/spikes/model_library.py`. This is the admission boundary for a future
redistributable model library; it is not evidence that vendor models or every
KiCad symbol are already supplied.

A runnable record binds a qualified `ModelPackage` to its exact content digest,
implementation identifier, validity envelope, and redistribution policy. An
approval is valid only when it names that exact digest, contains a non-empty
license expression and license-evidence digest, records a reviewer, and
explicitly permits redistribution. A changed model therefore loses its
approval rather than inheriting stale licensing evidence.

A KiCad mapping binds an exact `Library:Symbol` name and model digest to a
complete one-to-one symbol-pin/model-pin map. Duplicate targets, missing model
pins, mutable mappings, non-finite overrides, duplicate model IDs, and duplicate
symbol mappings are rejected. The versioned JSON index is deterministic and is
revalidated on load.

The current tests qualify the contract behavior only. Populating the index
requires separate provenance, license, parameter-fit, validity-envelope, and
numerical qualification evidence for every redistributed model. Generic SPICE
model ingestion and normalization remain outside this contract.
