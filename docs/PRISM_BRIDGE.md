<!-- SPDX-License-Identifier: Apache-2.0 -->
# Prism bridge: SPIKE-owned snapshot exchange v1

The [experimental source package](../integrations/prism/README.md) supplies a
bounded local exchange API for a future Prism extension. The package uses the
existing SPIKE process extension SDK, KiCad importer and preflighted-analysis
worker handler. It neither implements a Prism host nor introduces a solver.
Only `capabilities`, `list_solvers` and `run_preflighted_analysis` can be called
by this boundary. Requests cannot select arbitrary worker methods or commands.

## Source checkout workflow

Use an approved SPIKE Python environment and keep the package under
`integrations/prism` in the same source checkout. The entrypoint locates the
checkout's `python/spike_core` runtime. Set `SPIKE_EXTENSION_PATH` to the
checkout's `integrations` directory before starting SPIKE, then review and
trust `spike.prism-bridge` for that worker session. This directory is deliberately
outside the automatically trusted built-in `extensions` root. The manifest is
experimental, unbundled, and requests `filesystem.workspace`, `design.read`
and `results.write` for its declared importer and analysis contributions.

SPIKE's managed extension installer relocates package files and does not make
the source checkout runtime available to this entrypoint. Managed installation,
frozen installers and execution on other operating systems are not qualified
by this source preview. The extension host excludes arbitrary `PYTHONPATH`
variables; setting one is not a managed installation solution.

The existing SDK supervises its extension process using the manifest's
300-second timeout and 64 MiB result bound. The standalone `bridge.py` endpoint
requires its caller to supervise timeouts. The selected existing solver may
have further runtime requirements. Cancellation and orphan cleanup for any
external-engine child process are not verified here. Trust permits local code
execution; these permissions are not a complete operating-system sandbox.

## Requests and board snapshots

The versioned schemas are
[request](../schemas/prism-request-v1.schema.json),
[board snapshot](../schemas/prism-board-v1.schema.json) and
[result](../schemas/prism-result-v1.schema.json). They reuse the existing
[AnalysisSpec](../schemas/analysis-spec-v1.schema.json),
[SpiDeR](../schemas/design-ir-v1.schema.json) and
[AnalysisResult](../schemas/analysis-result-v1.schema.json) schemas. Resolve
these references from the local SPIKE schema registry; `spike.local` is an
identifier namespace and does not need a network fetch.

Every request has `contract: "spike/prism-request/v1"`, integer `api_version: 1`,
a plain 1-128 character `request_id`, and one operation:

| Operation | Required payload | Result |
| --- | --- | --- |
| `capabilities` | Neither source nor AnalysisSpec | Original capability and solver catalog data |
| `inspect-board` | `source` only | Imported, normalized SpiDeR with source binding |
| `analyze` | `source` and explicit `analysis_spec` | Original preflight diagnostics and analysis, with production provenance |

The source object has exactly `file_name`, `encoding`, `data` and `sha256`.
`file_name` is a portable basename ending in `.kicad_pcb`; absolute paths,
traversal and reserved device names are rejected. `encoding` must be `utf-8`.
`sha256` is the lowercase SHA-256 of `data.encode("utf-8")`. Preserve all saved
text, including newline characters. Read the source as bytes before decoding:

```python
import hashlib
import json
from pathlib import Path

board = Path("C:/Projects/Example/board.kicad_pcb")
payload = board.read_bytes()
snapshot = {
    "file_name": board.name,
    "encoding": "utf-8",
    "data": payload.decode("utf-8"),
    "sha256": hashlib.sha256(payload).hexdigest(),
}
board_exchange = {
    "contract": "spike/prism-board/v1", "api_version": 1, "source": snapshot,
}
Path("board.prism-board.json").write_text(
    json.dumps(board_exchange, ensure_ascii=False, allow_nan=False), encoding="utf-8"
)
# This file must describe the current intended setup, including explicit terminals.
analysis_spec = json.loads(Path("explicit-analysis-spec.json").read_text(encoding="utf-8"))
request = {
    "contract": "spike/prism-request/v1", "api_version": 1,
    "request_id": "board-study-1", "operation": "analyze",
    "source": snapshot, "analysis_spec": analysis_spec,
}
Path("request.json").write_text(
    json.dumps(request, ensure_ascii=False, allow_nan=False), encoding="utf-8"
)
```

An explicit AnalysisSpec requires `contract`, `mode`, `net_names`, `sources`,
`loads`, `return_path`, `probes`, `mesh`, `limits` and `options`. It accepts only
the existing AnalysisSpec top-level fields. Source/load/probe entries must be
objects, and net/capability entries must be strings. Declared `position_mm` or
`at` values must be finite two/three-coordinate arrays or explicit `x`/`y`
objects with optional `z`. Positions use the original source coordinates in
millimetres. Nested solver settings remain subject to the existing preflight
and solver contracts; the bridge does not infer terminals or fill missing
material, R/L/C or thermal data.

Run from the SPIKE checkout:

```powershell
.venv/Scripts/python.exe -B integrations/prism/bridge.py --request request.json --result result.json
```

The original source and request are preserved. Only a temporary exact snapshot
and the selected output exchange are written. Output is validated before an
atomic replacement. Request/output aliases, including hardlinks, are rejected;
the SDK importer also protects the selected `.prism-board.json` source from
being used as its output. An invalid or inaccessible output path may prevent
writing diagnostics, in which case exit code 2 and stderr identify the failure.

## Bounds and deterministic design identity

Requests and results are limited to 64 MiB each; source UTF-8 data is limited
to 32 MiB. The decoder rejects duplicate object keys, non-finite values,
non-UTF-8 text and nesting deeper than 32 levels. Protocol envelopes and the
AnalysisSpec reject unknown top-level fields. Solver-specific dictionaries
remain extensible under the existing contracts. Schemas describe structure;
runtime checks additionally enforce exact byte lengths, hashes, finite numbers
and alias protection.

The existing KiCad importer runs on a temporary snapshot. The bridge replaces
its temporary `source_path` with the original basename. Native source IDs,
coordinates and imported geometry are retained. Each component's
`model_resolved` is cleared because installed KiCad model roots can resolve the
same source reference to different machine-local paths. Its original
`model_path` reference is retained. `metadata.prism_snapshot_policy` records
the omission, and `PRISM_DEPENDENT_ASSETS_OMITTED` warns that dependent 3D assets
were not supplied. Asset-dependent analyses need a separately reviewed,
asset-aware exchange. This normalization does not substitute geometry or
invent a computed physical result.

The design digest uses the exact normalized SpiDeR, canonical JSON sorted by
key, compact separators, UTF-8 and `ensure_ascii=False`. Both ends need a
compatible SPIKE importer and the same source-only normalization policy.
Changes to geometry, metadata, importer version or retained issues can change
the digest and correctly invalidate admission.

## Result identity and native admission

Results use `spike/prism-result/v1` and echo the valid request ID, operation
and canonical request SHA-256. Parse failures may have null request identity.
`source_binding` records basename, exact source hash and UTF-8 byte count.
`design_binding` records design ID and normalized SpiDeR digest.
`analysis_spec_binding.sha256` binds the exact explicit settings supplied; the
unchanged settings are included as `analysis_spec`.

`analysis` retains the existing `spike/preflighted-analysis/v1` envelope,
including preflight issues and failed/blocked AnalysisResult data. At production,
the bridge adds these lineage fields to the actual AnalysisResult provenance,
rejecting any conflicting existing value:

- `design_id`
- `design_digest_sha256`
- `input_source_sha256`
- `input_analysis_spec_sha256`

All other provenance, solver status, model status, summary, fields, networks,
probes and issues remain as computed. These hashes detect stale or accidentally
swapped data; they are not signatures authenticating untrusted producers.

After trusting the package, import `board.prism-board.json` through SPIKE's
normal design importer registry. Use that exact normalized host design when
invoking `prism-import-result`. Supply `parameters.exchange` and the digest
of the host's current explicit AnalysisSpec, not a digest copied blindly from
the incoming exchange:

```python
import hashlib
import json
from pathlib import Path
from python.spike_core.automation import SpikeAutomation

worker = SpikeAutomation()
worker.call("trust_extension", {"extension_id": "spike.prism-bridge"})
# Exported from the host after importing the matching .prism-board.json snapshot.
host_design = json.loads(Path("host-design.spike-design.json").read_text(encoding="utf-8"))
current_spec = json.loads(Path("explicit-analysis-spec.json").read_text(encoding="utf-8"))
canonical = json.dumps(current_spec, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False).encode("utf-8")
exchange = json.loads(Path("result.json").read_text(encoding="utf-8"))
outcome = worker.invoke_extension(
    "spike.prism-bridge", "prism-import-result", design=host_design,
    parameters={"exchange": exchange,
                "expected_analysis_spec_sha256": hashlib.sha256(canonical).hexdigest()},
)
result = outcome["data"]["analysis_result"]
```

The importer recomputes the host and incoming design bindings and the included
spec digest, checks the current expected settings digest, and requires all four
matching provenance fields already present in the raw result. It never adds
missing input hashes during admission. The existing `admit_analysis_result`
then enforces status, model validity, solver provenance, finite visualization
data, sample bounds and validation evidence. The SDK host performs its normal
result admission before native viewers and reports receive the result.

## Status and recovery

The endpoint returns code 0 for a completed or blocked exchange and code 2 for
an error. Completion means the requested boundary operation completed, not
that its physical model became validated. Always read the exchange status and
the original model status before using data.

| Condition | Concrete recovery |
| --- | --- |
| Invalid snapshot hash or encoding | Recreate the snapshot from exact saved UTF-8 bytes; preserve newlines and recompute the source hash. |
| Missing SPIKE runtime or solver dependency | Use the approved source checkout environment; inspect `capabilities` and `list_solvers`, then install/configure the selected solver's documented dependencies. |
| `blocked` preflight | Inspect `analysis.preflight.issues`; correct explicit source/load positions, net/layer selection, scope or required setup, then rerun. No failed data is admitted. |
| Failed/nonconverged analysis | Retain `analysis.analysis_result` and its original fields/issues as diagnostics; resolve its reported setup, model or convergence issue and rerun. |
| Stale settings, missing lineage or design mismatch | Reimport the matching snapshot and produce a fresh analysis with current explicit settings. Do not rewrite hashes to relabel old fields. |
| Missing dependent geometry | Use an asset-aware workflow if the selected analysis needs 3D assets; the source-only warning is not evidence that those assets were solved. |
| Timeout or output failure | Use the supervising host's diagnostic log, check its output permissions/bounds, reduce scope when needed, and verify no external engine remains running before rerunning. |

The preview's focused tests exercise exact UTF-8 snapshots, normalization,
finite/depth/byte bounds, atomic writes and alias protection, malformed-input
diagnostics, status preservation, offline schema resolution, a real routed DC
analytic reference and standard SDK importer/result process calls. They also
reject a 2 A result swapped into a 1 A exchange and each missing production
binding. The staging process test uses a test-only runtime bootstrap; it does
not qualify a relocated package, a frozen installer or a running Prism host.
