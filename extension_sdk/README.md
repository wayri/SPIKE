# SPIKE Extension SDK

SPIKE extensions are local process modules described by
`spike/extension/v1`. They can contribute applications, commands, analyses,
importers, exporters, reports, schema-driven panels, and validators. A solver
that consumes `DesignIR` can use a declared analysis contribution. Existing
solver plugins may continue using the solver SDK.

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

For a simpler desktop install, open **Extensions → Browse and manage extensions →
Browse**. Choose a `.zip` or `.spike-extension` archive, or enter a local package
directory. SPIKE previews the manifest, permissions, file count, and package
SHA-256 before **Install extension**. The package is copied into SPIKE's managed
extension directory and appears immediately in the catalog. An update replaces
only a package previously installed by this manager and revokes session trust.
On **Manage**, select an extension to review and trust its permissions, run a
capability, or **Remove** a manager-installed package. Built-in and externally
discovered packages cannot be removed by the manager.

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

An extension may declare host-rendered UI metadata in its manifest:

```json
"ui": {"menu_bar": true, "title_bar": true, "menu_items": ["my-action"]}
```

`menu_items` must name declared contributions. SPIKE retains this metadata for
manifest compatibility; the current desktop UI displays each extension's
declared capabilities in its shared toolbar. Extensions do not inject webview
code. Installed extensions appear under the
shared **Extensions** menu and in the **Extensions** ribbon tab. The ribbon has
an extension selector and shows its declared capabilities. A capability opens
its setup in the manager so inputs can be reviewed before execution. Users can
independently show or hide each extension in the shared menu and toolbar from
**Manage**. Visibility is saved as a local application preference. An untrusted
extension remains visible but cannot run until explicitly trusted for the
session.

See `../extensions/net-inventory` for a complete Python example.
The bundled `../extensions/openems_suite` package shows a multi-workflow
external solver integration for PI and SI. OpenEMS itself has no native thermal
solver; its extension exposes no thermal contribution.

## External analysis round trip

Declare an `analyses` contribution with `output_contract: "spike/v1"` and both
`design.read` and `results.write` permissions. The host passes a normalized
`spike/v1` DesignIR in `context.design` and a SHA-256 binding in
`context.design_binding`. Return a completed `spike/v1` AnalysisResult as
`data.analysis_result` inside the extension result envelope. Its provenance
must include the input `design_id`, `design_digest_sha256`, and solver identity.
The host checks those fields and admits finite, bounded visualization samples
before adding the result to the normal result viewer, history, and reports.

For mesh-aware analyses, declare `mesh.read` in addition to `design.read` and
`results.write`. The host supplies a complete bounded hybrid topology mesh,
a separate sampled display preview, normalized analysis settings, and solver
geometry with materials and excitations. Truncated or erroneous topology is
rejected. Return the mesh SHA-256 in `provenance.input_mesh_sha256` and the
analysis setup SHA-256 in `provenance.input_analysis_spec_sha256` (the Python
helper does this automatically) and publish computed fields or explicit mesh
cells through `fields.visualization`. See the
[mesh-aware example](examples/mesh-field-adapter/extension.py). This exchange
does not establish mesh convergence or qualify solver physics.

The dependency-free [Python helper](python/spike_extension_sdk.py) constructs
the bound result and writes the envelope atomically. See the
[analysis integration guide](../docs/EXTENSION_ANALYSIS_API.md) for the exact
request, field names and units, scripting workflow, and an adapter example.

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
locations and the explicit SPIKE state and OpenEMS runtime paths so installed
optional runtimes can be discovered. It does not copy
arbitrary environment variables or credentials. Extensions remain trusted local
processes, not an OS security sandbox.
