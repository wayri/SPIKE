# ADR 0024: FreeCAD as a SPIKE worker client

Status: accepted for the source workbench, 2026-09-28.

## Context

The FreeCAD companion already owns mechanical assembly and inert geometry
exchange. FreeCAD's bundled Python cannot be assumed to match SPIKE's solver
environment. Running numerical work on the GUI thread would freeze FreeCAD and
would create a second, unqualified solver path.

## Decision

The workbench can launch the user-configured local SPIKE source worker with
`QProcess`, fixed `-m python.spike_core.service` arguments, and the existing
JSON-line method/params protocol. The worker retains importer, solver,
preflight, capability, and result authority. The FreeCAD panel accepts explicit
JSON analysis inputs, shows the returned status, and can save the response.
Each request uses a separate process so cancellation terminates the worker
process. External engines launched by a worker retain their own process
supervision policy. Responses are capped at 64 MiB. The linked KiCad file is read
through SPIKE's importer; source SHA-256 is checked before analysis. Component
positions are point references, not physical package geometry.

## Consequences

FreeCAD can access new worker methods without duplicating solver code, but
method-specific setup remains documented by the SPIKE contracts. The user's
Python environment must contain SPIKE runtime dependencies. FreeCAD edits do
not mutate KiCad or silently change electrical DesignIR. Approved mechanical
changes still use the reviewed collaboration contract. A future result mapper
needs its own identity and geometry contract; this panel does not infer fields
or validation from CAD solids.
