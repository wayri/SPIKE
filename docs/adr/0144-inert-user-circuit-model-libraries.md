# ADR 0144: Inert user circuit-model libraries

- Status: accepted for experimental development, 25 October 2026
- Owners: Python import/application services; TypeScript presentation

## Decision

Replace the workbench's first-header regex import with bounded backend
inspection followed by explicit entry selection and import. Reuse existing
workspace source, assignments, pin maps, persistence and engine execution.
Keep model discovery independent of simulation and executable registration.

Imported source is self-contained within the admitted strict subset. Includes
are never resolved. Import provenance records source identity and user notes,
not executable trust, device validity or sharing rights. Composition reparses
the current source, verifies pin order and rejects conflicting library symbols.
Identical dependency definitions are emitted once. Legacy workspaces without
import metadata retain their existing composition behavior.

This is a parser/application increment with no new numerical formulation or
engine/device support. General extraction and protocol capabilities continue
through existing solver/extension registries and their independent gates.
See the [workflow, limits and next stages](../USER_MODELS_AND_BACKENDS.md).

## Verification

Check multi-entry and continuation parsing, parameter and pin identity,
dependency closure/arity/cycles, source and metadata budgets, hostile syntax,
cross-library conflicts, exact worker wrappers, non-execution and saved-data
round trips. UI checks include stale source/results, byte limits before file
read, close/unmount behavior, disabled/error/recovery states, wildcard search
and wide/narrow presentation. Native installed visual acceptance remains a
separate release check.
