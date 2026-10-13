# ADR 0067: Retained-volume assembly EM execution

Status: implemented, experimental and unvalidated.

Add a separate Python execution contract for freshly admitted tetrahedral
material volumes and explicit conductor-face ports. Emit CSXCAD polyhedra in
metres, retaining cavities and ownership. Preserve metadata-only handoff behavior.
Reuse managed runtime discovery, isolated immutable source, process quotas and
heavy-worker lifecycle. Rust remains infrastructure-only.

Results bind geometry, complete request and invocation and retain actual E/H
artifacts. No automatic copper extraction or assumed connector geometry crosses
this boundary. A synthetic benchmark does not qualify the enclosed Arduino study.
See [execution and validity](../RETAINED_ASSEMBLY_EM.md).

ACC03 reporting refinement, 2026-10-13: retain separate process-completion,
requested-decay stopping and observable-sensitivity evidence. A bounded,
versioned native-log parser may return unknown; it must not infer convergence
from normal exit or absent warnings. Configuration mismatches, stale samples
and malformed/nonfinite evidence withhold success. Historical duration-only
metric aliases remain labeled as duration, not timestep, comparisons. This
does not change the solver cap, requested decay, production flag or numerical
backend. See the exact-stopping section of the execution document.
