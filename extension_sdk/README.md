# SPIKE Extension SDK

SPIKE extensions are local process modules described by
`spike/extension/v1`. They can contribute applications, commands, analyses,
importers, exporters, reports, schema-driven panels, and validators. A solver
that consumes `DesignIR` should continue to use the stricter solver SDK.

## Package layout

```text
my-extension/
  spike-extension.json
  extension.py
```

Set `SPIKE_EXTENSION_PATH` to one or more parent directories containing
extension packages. SPIKE discovers `*/spike-extension.json` beneath each
root. Unbundled extensions are catalogued but cannot execute until their ID is
explicitly trusted.

## Process protocol

SPIKE launches the declared entrypoint with:

```text
--request <job>/request.json --result <job>/result.json
```

The request contains the manifest, contribution ID, and only the context fields
allowed by the manifest permissions. The extension must write:

```json
{
  "contract": "spike/extension-result/v1",
  "status": "completed",
  "title": "Result title",
  "data": {}
}
```

The process runs with a minimal environment, a temporary working directory,
bounded runtime, bounded result size, and no shell. This is process separation,
not a complete operating-system sandbox. Only trust code you would otherwise
run locally. Future packaged releases should add platform sandboxing and signed
bundle verification.

## UI contributions

Third-party JavaScript is not loaded into the Tauri webview. Applications and
panels return structured data or a schema-driven view description. This keeps
extensions portable between desktop, CLI, and future cloud workers.

See `../extensions/net-inventory` for a complete Python example.

## Design and harness extensions

Executable design importers can participate in the normal importer registry.
Declare `output_contract: "spike/v1"`, `source_formats`, `extensions`, and optional
`accepts_directories`. The host sends `context.source` under the
`filesystem.workspace` permission and expects `data.design` in the extension
result. Source policy and options travel with the request.

`schemas` and `harness_engines` are additional contribution points.
`context.harness` requires `harness.read`. See the bundled `odb-import` and
`harness-engine` packages and [ODB/harness guide](../docs/ODB_AND_HARNESS_EXTENSIONS.md)
for contracts, examples, supported scope, and qualification limits.

## Mechanical exchange and downloadable artifacts

The bundled `mcad-export` extension contributes preview, schema and export actions.
It uses [mechanical assembly v1](../schemas/mcad-assembly-v1.schema.json), with
stable IDs, parent assemblies, rigid transforms, material references, and explicit
geometry. See [MCAD collaboration](../docs/MCAD_EXPORT.md) for the supported solids,
coordinate convention and qualification limits.

Export results can use `data.contract: "spike/artifact-export/v1"` (or the specialized
`spike/mcad-export/v1`) and an `artifacts` array following
[export-artifact.schema.json](export-artifact.schema.json). Each artifact contains
a plain `file_name`, `media_type`, `encoding` (`base64` or `utf-8`), `data`, and the
SHA-256 of decoded bytes. The host offers a native save dialog; result content
cannot select an output path. Supported suffixes are STEP/STP, ZIP, JSON, FCStd
and BREP. The host rejects invalid base64, digest mismatches, path-like names and
files over 64 MiB. `manifest` may describe verification, provenance and omissions.

The minimal process environment now includes standard OS home/application
locations so installed optional runtimes can be discovered. It does not copy
arbitrary environment variables or credentials. Extensions remain trusted local
processes, not an OS security sandbox.
