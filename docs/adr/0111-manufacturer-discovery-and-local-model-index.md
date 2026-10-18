# ADR 0111: Separate product discovery from executable model qualification

Status: accepted for engineering-preview implementation, 2026-10-19.

The generic parameter grid does not satisfy manufacturer-part discovery.
The native hub separates product identities, sourced electrical part records
and local LTspice metadata. Generic models are not renamed to inflate coverage.

The factual discovery JSON uses `spikes/manufacturer-discovery/v1`. Each
identity records manufacturer, product, category, official source, check date
and explicitly unqualified model-source state. It is not a package pinout,
ordering-code database or executable-model package. Existing numerical and
release gates remain unchanged.

The local adapter uses `spikes/ltspice-local-library/v1`, retaining paths and
raw-file hashes without embedding third-party model bodies. It reuses the
established declaration inspection boundary. Includes and native code never
execute during indexing. Bounded traversal, byte limits and diagnostics remain
visible. Original bytes are rechecked before user-requested review/import.
No implicit hostile-code sandbox or redistribution permission is claimed.

The native parser admits supported intrinsic model cards before mutation.
Unsupported dialects, parameters and device families are rejected, not
normalized into a different physical device. No new governing equations or
numerical kernels are introduced.

Validation uses catalog contracts, index/admission fixtures, native wx
search/sort/model-link tests and frozen/installed checks. Exact executed counts
and candidate hashes belong with each package; this ADR is not qualification.
