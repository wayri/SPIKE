<!-- SPDX-License-Identifier: Apache-2.0 -->
# Prism snapshot bridge (experimental source preview)

This opt-in SPIKE process extension exchanges saved KiCad PCB snapshots and
results from SPIKE's existing import, preflight and solver services. It provides
a SPIKE-owned boundary for a future Prism integration. The Prism host and its
extension UI are not implemented by this package.

Keep the package at `integrations/prism` in a SPIKE source checkout. Run SPIKE
with that checkout's approved Python environment and set `SPIKE_EXTENSION_PATH`
to the checkout's `integrations` parent before the worker starts:

```powershell
$env:SPIKE_EXTENSION_PATH = 'C:/Projects/SPIKE/integrations'
```

Review `spike.prism-bridge` in the extension manager and explicitly trust it
for the current worker session. It remains experimental and `bundled: false`.
Placing it under SPIKE's built-in `extensions` root grants distribution trust
and defeats this opt-in boundary. The tested source workflow discovers it
outside that root. Managed installation copies the package away from its
checkout runtime, so managed and frozen installer execution are not qualified.

The package contributes these existing SDK extension points:

| Contribution | Purpose | Inputs |
| --- | --- | --- |
| `prism-capabilities` | Inspect installed capabilities and solvers | Empty parameters |
| `prism-import-board` | Import a saved snapshot through the normal design importer registry | `.prism-board.json`, `spike/prism-board/v1` |
| `prism-import-result` | Admit a completed analysis into native result workflows | `parameters.exchange` plus the SHA-256 of the current explicit AnalysisSpec |

The standalone boundary accepts `capabilities`, `inspect-board` and `analyze`:

```powershell
.venv/Scripts/python.exe -B integrations/prism/bridge.py --request request.json --result result.json
```

An analysis requires explicit source/load/return-path, net and solver settings.
Terminals are never inferred from a board. The endpoint writes a bounded atomic
result file and returns exit code 2 for an error. A blocked preflight returns
exit code 0 with `status: "blocked"`; always inspect status before importing.
Use a supervising host to impose a timeout on the standalone endpoint.

Source, normalized design and exact analysis settings are bound at production.
Import requires those existing bindings and the host's current settings digest;
it never supplies missing lineage. Solver fields, issues, statuses and model
status are preserved. The importer retains source coordinates and stable IDs,
normalizes the temporary source path to the basename, and omits machine-local
resolved 3D model paths. Original model references remain visible, with an
explicit warning that dependent 3D assets were not supplied.

This is trusted local process code, not an operating-system sandbox or a
cryptographically authenticated remote service. The bridge adds no solver and
makes no new physics qualification claim. External engine child cancellation
and orphan cleanup are not verified by this preview.

See [the exchange guide](../../docs/PRISM_BRIDGE.md) for schemas, exact-byte
snapshot creation, bound result import and recovery. See the existing
[extension SDK](../../extension_sdk/README.md) and
[analysis admission contract](../../docs/EXTENSION_ANALYSIS_API.md) for host
permissions and native result validation.
