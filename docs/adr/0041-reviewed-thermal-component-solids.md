# ADR 0041: Reviewed component solids and conformal thermal interfaces

Status: Implemented, experimental; numerical release requires human review.

## Decision

Promote only explicitly selected retained closed STEP component models to
AssemblyIR physical parts. Bind source component, model bytes, material and
reviewed mounting transform to the saved project identity. Display meshes do
not establish a closed solid or thermal material.

Generate multiple occurrences in one bounded world-space OCC job, preserve
source ownership, and split interface nodes into separate thermal unknowns.
Automatic linking prepares existing reviewed contacts from matching interface
triangles and their retained total resistance. Geometry alone supplies neither
contact resistance nor electrical connectivity.

Explicit `thermal_only_part_ids` let a promoted package receive heat already
represented by its board circuit, without adding a duplicate electrical device.
Retained electrical bonds to an excluded package are rejected. The editor makes
assembly rebinding and this modelling choice explicit and invalidates prior
prepared results when the draft changes.

## Consequences

Materials, mounting datums, boundary conditions and loss mappings remain
reviewed inputs. Overlap, unsupported STEP compounds, stale source identity and
resource exhaustion fail explicitly. Solver availability and a plotted mesh do
not establish spatial convergence or hardware qualification.

See [component solids and actual engine checks](../THERMAL_COMPONENT_SOLIDS.md)
and [native circuit coupling](../MULTIBOARD_VOLUME_ELECTROTHERMAL.md).
