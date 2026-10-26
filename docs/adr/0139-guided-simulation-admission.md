<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0139: Live, revision-bound guided simulation admission

Date: 2026-10-24. Status: accepted for source development; installed UI acceptance open.

## Decision

Use a live editor adapter registry for guided Run and Tutor. The editor owns its
current draft, readiness checks, repair destinations and existing run handler.
The shared controller owns one-required-item presentation, warnings, cancellation,
revision guards and duplicate-submission prevention. Header controls are present
in every workspace; only registered supported execution routes may become ready.
Opening an editor, tutorial or saved result never counts as executing a solver.

A check is not a solve. PI uses pure preflight_analysis; component thermal adds
validate_component_thermal reusing existing admission, surface branch, graph
sink reachability and work-budget checks. Existing numerical estimators reuse
the extracted helpers without changed equations or constants. SI and board
thermal reuse their existing input validation. EMI uses existing pre-pass
admission. OpenFOAM still needs a prepared case for the exact scenario. Generic
extension routes validate declared prerequisites while retaining engine-owned
runtime/numerical checks; dedicated engines retain their own execution controls.

Draft edits discard readiness without repeatedly meshing on each keystroke.
Recheck reads the current draft. Final Run checks again before dispatch and
retains all backend, resource, trust and capability gates. Source, project or
adapter revision changes cancel old readiness. No values, thermal paths, meshes,
physical connections or supported solver claims are inferred by the tutor.
The guide reserves layout space beside the editor/viewport or below at narrower
widths rather than using a modal that prevents repairs.

## Verification and limits

Controller/component tests cover blockers, warnings, cancellation, stale async
checks, duplicate clicks, fresh preflight on Run, tutor navigation and recovery.
Editor adapter tests exercise existing input predicates and verify no solve
occurs during readiness. Thermal tests patch out numerical estimators and cover
missing sinks, invalid values, transient limits and resource budgets alongside
existing solver regressions. Native classification retains worker supervision.
See [guided runs](../GUIDED_SIMULATION_RUN.md).

Readiness establishes required setup admission, not numerical validation,
convergence or hardware qualification. Unknown/dedicated workflows stay blocked
until their own supported controls are used. Installed desktop acceptance and
packaging remain separate checks; no release is authorized by a ready badge.
