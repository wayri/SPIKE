# SpiDeR interoperability API

SPIKE exposes a read-only worker API for inspecting and exchanging the existing
`spike/v1` SpiDeR document and the typed `spike/design-ir/v2` document. Validation
confirms interchange structure only. Every response states
`validation_is_not_solver_admission: true`; a valid document still requires the
ordinary analysis capability and model-admission checks before solver use.

## Operations

`handle_spider_request(method, params)` returns `None` for an unknown method and
a `spider/api-result/v1` object for a supported method.

| Method | Required parameters | Purpose |
| --- | --- | --- |
| `spider_capabilities` | none | Lists contracts, entity kinds, canonical units, features, and limits. |
| `validate_spider` | `document` | Reports malformed values, unsupported units, duplicate identities, dangling references, and revisions. |
| `normalize_spider` | `document` | Rehydrates and serializes the document, optionally to `target_contract`. |
| `query_spider` | `document` | Returns a stable page of canonical v2 entities, source identities, and outgoing references. |
| `compare_spider` | `before`, `after` | Returns a deterministic page of added, removed, or changed entity identities and source/frame drift. |

The exact request and result shapes are published in
`schemas/spider-api-request-v1.schema.json` and
`schemas/spider-api-result-v1.schema.json`. Documents are supplied inline. The
API does not read a caller-selected path, write result files, or mutate a design.
An inline document is limited to 8 MiB, 100,000 entities, 64 nesting levels,
and 1,000,000 JSON values. Query and comparison pages contain at most 500 rows.

## Revisions and identity

`document_revision` is SHA-256 over canonical JSON. `source_revision` uses the
declared v2 `source.source_digest` or v1 `metadata.source_sha256`; when neither
exists it is derived from the document revision and labeled accordingly.
Callers can pass `expected_revision` to `query_spider` to prevent paging across
different document snapshots.

Queries expose typed v2 canonical IDs and retained source IDs. A v1 query is
migrated to typed v2 in memory and reports that migration. Each row contains the
full entity plus sorted outgoing references with the referenced entity kind and
canonical ID. The response also includes the coordinate frame and canonical
millimetre/right-handed units so local coordinates are not mistaken for an
untransformed global frame.

Comparison matches a unique source ID within each entity kind, then falls back
to the canonical ID. This keeps source-native identity stable when revision-bound
canonical IDs differ. Changes are sorted by entity kind and identity before
pagination. Source and coordinate-frame drift are reported separately.

## Normalization and legacy projection

Normalization returns the document under `normalized_document`, its hash under
`normalized_revision`, and a `projection` report. Migration from v1 to v2 uses
the established typed migration and preserves legacy records in extensions.
Projection from v2 to v1 uses the established `SpiDeRV2.to_v1()` path, including
its rejection of arcs that cannot be projected.

`document_for_legacy_worker()` is the stricter service helper. It returns a v1
document only after a typed v2 to v1 to v2 semantic round trip. It rejects stale
v1 extension snapshots, changed typed geometry that the legacy snapshot would
hide, non-identity coordinate frames, and typed collections with no lossless v1
representation. The helper returns `{ok, document, report}`; `document` is null
on rejection. This check prevents silent loss, but does not establish that any
solver supports the design or requested analysis.

Unsupported and retained geometry remains explicit in the existing contracts.
The interoperability layer does not synthesize material properties, geometry,
connectivity, coordinate transforms, or other physical data.
