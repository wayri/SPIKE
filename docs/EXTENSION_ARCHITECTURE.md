# Extension Architecture

## Purpose

`spike/extension/v1` allows SPIKE to host engineering utilities and domain
applications that are not limited to SI or PI. The contract is transport
neutral and can be used from desktop, CLI, CI, or a future cloud worker.

The solver contract remains separate because numerical engines require stricter
geometry, capability-selection, result, provenance, and validation rules.

## Extension points

- `applications`: complete task-oriented tools presented by the shell.
- `commands`: focused operations callable from menus, automation, or CLI.
- `analyses`: non-solver analysis workflows and orchestrators.
- `importers`: source-to-normalized-model adapters.
- `exporters`: normalized-model or result exporters.
- `reports`: structured report-data providers.
- `panels`: schema-driven inspector or result views.
- `validators`: design, project, or result checks.
- `protocol_suites`: declarative `spike/si-protocol-suite/v1` setup definitions.

An extension can contribute to several points. Contribution IDs must be unique
inside the package.

## Runtime boundary

SPIKE discovers manifests without executing extension code. Invocation creates
a temporary job directory containing a JSON request and expects a bounded JSON
result. Entrypoints:

- resolve inside the extension package;
- run without a shell;
- receive a minimal environment;
- receive only context allowed by declared permissions;
- have bounded execution time and result size;
- must return `spike/extension-result/v1`.

Python extensions use SPIKE's packaged Python runtime. Native extensions launch
their packaged executable directly.

## Trust and security

Bundled extensions are trusted only when they are discovered under the
distribution-owned extension root. A manifest cannot make itself trusted by
setting `bundled: true`; such an external package is rejected. Unbundled
extensions are catalogued but cannot execute through the normal desktop path.
Future executable trust must bind publisher identity, full bundle digest,
version, and exact permissions rather than trusting an extension ID alone.

Process separation is not a complete OS sandbox. Signed package verification,
publisher identity, revocation, and Windows AppContainer/macOS sandbox/Linux
namespace enforcement are deployment gates before an unrestricted public
extension marketplace.

SPIKE never loads third-party JavaScript into its Tauri webview. Panels and
applications return structured data or schema-driven view descriptions. This
prevents an extension from sharing the UI's DOM and Tauri IPC privileges.

The SI Extension Builder has GUI and JSON-code authoring modes, but its active
output is declarative data only. Exported optional Python source is marked
dormant and is not installed or executed automatically. Code-assisted suites
remain blocked until deterministic package hashing/signing, approved-path
installation, resource limits, and OS sandbox enforcement are implemented and
tested on each supported platform.

## Compatibility

The optional [FreeCAD collaboration companion](FREECAD_COLLABORATION.md) builds
on MCAD exchange while using host-owned, manifest-bound worker operations for
project updates. Its installable FreeCAD workbench performs interactive editing;
the SPIKE webview receives structured session/feedback data. Numerical thermal
execution remains a separate solver-adapter milestone.

The manifest declares both a contract and integer API version. Unknown manifest
fields, extension points, permissions, states, and runtimes are rejected.
Breaking changes require a new contract or API version. Additive result data
belongs under the result `data` field.

## Distribution

Development roots are supplied through `SPIKE_EXTENSION_PATH`. Each root
contains one or more package directories:

```text
extension-root/
  vendor.extension-name/
    spike-extension.json
    extension.exe
```

Production packages should be immutable archives with a signed file manifest,
license metadata, dependency inventory, and platform/architecture declarations.
