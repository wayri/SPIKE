<!-- SPDX-License-Identifier: MIT -->
# ADR 0022: Design-bound external analysis results

- Status: Accepted for the local engineering preview; not solver qualification.
- Date: 2026-09-24

## Context

Process extensions could inspect DesignIR and return arbitrary structured data,
but their analysis results did not enter the normal visual, project, or report
workflow. An external adapter also needed a safe way to identify the exact
board snapshot on which it ran.

## Decision

An extension declares an `analyses` contribution with `output_contract:
"spike/v1"` and `design.read` plus `results.write`. The host passes normalized
DesignIR and a canonical JSON SHA-256 binding. The extension returns a
`spike/v1` AnalysisResult inside `data.analysis_result`, including matching
board provenance, solver identity, explicit model status, and optional
`spike/result-visualization/v1` fields. The worker admits only completed,
design-bound, finite, size-limited results and attributes the extension ID.
The desktop then uses its existing result ingestion path.

The extension protocol remains a process protocol. The host does not load
third-party JavaScript into the webview. External packages require explicit
session trust after discovery. A Python automation facade uses the same worker
methods and admission path; it is not a second solver contract. A `results.read`
permission allows bounded existing-result context for downstream tools.

## Consequences

External engines can exchange board data, result fields, networks, probes,
reports, and visualization data without implementing the internal solver.
Admission verifies structure and provenance but cannot prove that returned
physics is accurate. Validated claims require supplied evidence and still need
the project's knowledgeable human review before release. Trust is local to a
worker session; process separation is not a complete OS sandbox.
