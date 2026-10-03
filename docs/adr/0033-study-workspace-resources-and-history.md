<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0033: Study workspace resources and captured history

- Status: Accepted for the local engineering preview.
- Date: 2026-10-03

## Context

The original study manager stored ordered cases and a single captured result.
Capturing again replaced that result, changing setup removed it, and datasets
were disconnected from the project study. A larger investigation needs a
searchable collection of definitions, captured results, and source data while
preserving each solver's provenance and admission rules.

## Decision

Extend the existing version-one frontend study projection with optional tags,
archive state, attached datasets, case-to-dataset associations, and captured
history. Preserve the legacy current `resultSnapshot` and `resultRef` fields
and their existing activation and invalidation behavior. A captured-history
record freezes the provided setup and scenario and retains the original result
payload. Its timestamp records capture, not solver execution or qualification.
Changing a case invalidates its current result without rewriting history.
Duplicating a case copies definitions and data associations without copying
results or asserting that a solve occurred.

The manager provides study navigation, a simulation table, and a detail
inspector. Search, archive, import/export, data linking, recorded-result review,
and compatible side-by-side comparison remain presentation and organization
features. They do not schedule solvers, reinterpret units, or manufacture job
states. Numerical execution and admitted result activation remain owned by the
existing domain adapters. Coupled multiboard studies retain their separate
request/result digest contracts.

Dataset parsing and persistence use explicit bounds and safe JSON admission.
Unsupported data is not promoted to a numerical result. Project copies made
without results strip captured-result payloads and result-derived dataset data
and references while retaining study definitions and source data. All new
fields remain optional so old version-one projects reopen.

SPIKE and the independent offline SPIKE-Em repository carry their own source
implementation; neither imports a sibling tree at runtime. SPIKE-Em presents
RF, EMerge, and Optycal workflows and preserves inherited PI and Thermal cases
as suspended records.

## Consequences

History adds bounded project storage. Capture limits and import errors must be
visible, and users explicitly manage retained records. Exported payloads retain
source units, status, model limitations, and design identity. Comparison is not
evidence of compatible physics or validated solver accuracy. The general study
projection does not replace authoritative version-three result artifact indexes.
