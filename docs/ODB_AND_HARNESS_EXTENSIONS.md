# ODB++ and harness extensions

Status: engineering preview. These extensions are not a claim of native-file
support for every ECAD vendor, or production qualification against their exports.
They use SPIKE's normal DesignIR, import-report and isolated extension process
contracts. No proprietary CAD SDK or third-party JavaScript is loaded in the UI.

## Using the desktop

Use **File → Import ODB++ archive** for ZIP, TAR, TGZ, TAR.GZ, or ODB archives,
or **File → Import ODB++ folder** for an extracted job. The Extension Manager
route remains available for explicit importer options. Jobs containing several
steps require a step name in the extension/import options, for example
`{"step": "pcb"}`. Panel step repeats are reported as unsupported; selecting a
board step avoids accidentally treating a panel as one board.

The imported board opens in the regular viewport. Copper holes are displayed as
holes. Circular arcs are tessellated for display only; the exact records are
passed to the PI dialog and other solver workflows. The extension result shows
the import-quality report. A `.spike` save retains the normalized source,
canonical DesignIR, vendor metadata, model asset bytes and harness document.
The normalized snapshot is not the original compressed ODB archive: retain the
original export separately. Its digest and original path remain provenance.

Open **Harness Engineering** to import a connection list, create a document,
edit wire nets and lengths, check connectivity, compile an electrical fragment,
or export JSON. Connection definitions and arbitrary properties can be edited
in the document editor. Run validation after edits and save the project.

## Command line and process API

```text
python -m python.spike_core.cli import board.tgz --format odb++ --step pcb --report
```

Worker `load_design` and `import_design_v2` accept `path`, `format_hint`, and an
`options` object containing `step`. `import_design_v2` with `include_snapshot`
returns a display snapshot as well as the typed design and quality report.
The desktop also sends `snapshot_only: true`. That response retains canonical
DesignIR and returns each large ODB collection once so real jobs fit the bounded
JSON-lines transport. Consumers must honor
`canonical_design.metadata.transport_projection`: canonical zones replace an
omitted duplicate `design.zones`, and canonical metadata is authoritative for
`odb_artwork`. This is a transport projection, not a lossy project format.
Before the desktop saves a large normalized project it wraps `source_board` as
`spike/normalized-source-zlib/v1`, with zlib-compressed base64 UTF-8 plus the
uncompressed byte count and SHA-256. The backend verifies and expands this
wrapper supplied either as an object or as its JSON string before validating or
writing the project. Decompression is bounded to the declared size and 512 MiB.
Compact project reopen uses
`compact_normalized_source: true`; its wrapper may set
`canonical_design_omitted: true`, in which case the caller must inject the
authoritative `result.canonical.design_ir` before normalizing the snapshot.
Importer selection is a registry operation; filename matching selects a parser
but does not establish that the package is valid.

Executable extension importer contributions declare `output_contract: spike/v1`,
`source_formats`, `extensions`, and optional `accepts_directories`. The host
passes a permission-filtered `source` context containing an absolute path,
ImportPolicy and options. The extension returns `data.design`. Untrusted and
disabled extensions cannot execute. Import deadlines also bound the process.

The SDK additionally exposes `schemas` and `harness_engines` contribution points,
and a `harness.read` context permission. Harness actions use `context.harness`;
imports use `context.parameters.path`. The existing process boundary is not an
OS sandbox: trust remains required for external code.

## ODB++ coverage

The implementation follows the [Siemens ODB++Design format specification](https://odbplusplus.com/design/odb-design-format-specification/).
It reads matrix layer/step definitions, independent file units, symbol units,
profiles, positive circular strokes, arcs, round/rectangular/oval/elliptical pads,
rounded-rectangle flashes, positive surfaces with explicit contours/cutouts,
circular and oval/slot drill hits,
component placements, EDA NET/SNT/FID links and toeprints. Matching circular via
lands and a unique drill establish a via only when the declared spans agree.

Component properties are ordered records, so duplicate vendor property names
are preserved. BOM records, package geometry records, attribute assignments,
lookup candidates, source feature indices and available UIDs remain available.
An integer attribute is not automatically reinterpreted as a text lookup.

The standard stackup XML resolver follows EdaData material/spec references and
explicit property selection. It resolves default/finished thickness, material
units, and unambiguous dielectric properties. Supplier alternatives and
frequency tables remain in the retained XML when they cannot be selected
unambiguously. Unknown thickness and dielectric properties are not invented.

Unsupported donut and other custom/resized symbols, negative layer/feature compositing, text
copper, unresolved holes/padstacks, panel instances and malformed geometric
records are reported with retained source evidence. These omissions block
electrical readiness. Copper thickness must be explicit for ODB++ solver runs;
AC/SI also require a complete physical stackup. The solver registry enforces
the gate even when a caller bypasses the desktop report.

The import report separates exact issue totals from bounded representative
samples and from severity. A large number of technical-layer warnings cannot
hide a later copper error. `geometry_solver_ready` is computed from total error
counts, not from the sampled issue list. Correct a source/export problem and
reimport; do not edit the report to clear readiness. For multi-step jobs, select
the intended board step. For stackup warnings, provide explicit stackup data or
the enrichment file described below. Keep the original archive or folder when
using source-record lookup and reimport recovery.

Canonical snapshots retain package, subnet, drill, artwork, and source identity
data. Large zone source records use the authenticated
`spike/odb-source-table/v1` (`zlib+base64+json`) table; readers must verify its
SHA-256 and count through `decode_odb_source_table` before using it. This keeps a
saved project self-contained without multiplying the same raw surface records.

## Explicit enrichment and model assets

`steps/<step>/spike/board.json` optionally uses
[`spike/board-enrichment/v1`](../schemas/board-enrichment-v1.schema.json).
It can supply physical stackup and attach properties and component models that
were not exported. Model paths are relative to the ODB job root, with explicit
row-major 4×4 affine transforms in millimeters and optional SHA-256 assertions.
Assets are retained by digest, so archive imports do not depend on expired
extraction directories. Retention does not validate STEP geometry or create
tessellations; viewport display of STEP/VRML assets still requires the existing
model/tessellation workflow. Vendor parameter names are preserved, not mapped
speculatively onto electrical models.

## Harness interchange

[`spike/harness/v1`](../schemas/harness-v1.schema.json) describes connector pins,
splices, wires, cable membership, twist/shield metadata, optional 3D routes,
board bindings, vendor properties, provenance and namespaced extensions.
Lengths use mm, areas mm², resistance Ω, inductance H, capacitance F and
conductance S. IDs, including pin numbers such as `01`, remain strings.

CSV/TSV connection lists require `wire_id`, `from_connector`, `from_pin`,
`to_connector`, `to_pin`. Optional fields include `net`, `color`, `part_number`,
`length_mm`, `area_mm2`, `resistance_ohm`, and `inductance_h`. A `column_map`
maps these field names to the source export's headers; delimiter can be comma,
semicolon, tab or pipe. Every original row and unrecognized property survives.
This supports explicit mappings of connection-list exports from other tools;
it is not a parser for their proprietary harness databases.

Validation rejects duplicate identifiers, unknown terminals, self-connections,
invalid physical values, duplicate cable membership, inconsistent net labels,
overfilled terminals, dangling splices, required open pins and too-short routes.
The graph and BOM distinguish known cut length from unspecified wire length.

The circuit compiler accepts explicit resistance or computes `rho * length /
area` when all three are provided. Material-derived values are at the material's
reference temperature. Inductance and shunt values remain explicit, with an
explicit reference terminal required for shunts. It does not infer ground,
connector contact resistance, shielding effectiveness, mutual coupling or a
field solution from a wire gauge or material label.

`harness-bind` bridges point-to-point documents into the existing multiboard
harness compiler. It requires exact connector board bindings, matching pin maps
and lengths, and explicit positive inductance. Splice networks and unbound
shunts fail closed. The emitted circuit remains a fragment until board ports,
return paths and the other existing coupled-network requirements are supplied.

## Verification and remaining qualification

See the [public-board validation matrix](../benchmarks/public-board-corpus/REPORT.md)
for measured imports, native KiCad comparisons, reproducible downloads and
remaining failures on real boards. ODB++ remains an engineering preview.

`tests/python/test_odb_harness_extensions.py` covers archive variants, nested
gzip, unsafe paths/links, size limits, deterministic identity, typed geometry
and property round trips, source-loss gates, stackup XML, model-byte retention,
process trust, CSV mappings, harness graph/physics checks, multiboard binding,
and project save/reload. `app/scripts/test-normalized-board.mjs` checks display
arcs and cutouts without changing exact solver data.

The worker packaging gate also executes both extensions in the frozen runtime,
loads their bundled schemas, compiles a harness circuit, and normalizes an ODB++
probe. Python extension processes use the frozen worker's dedicated extension
host. The Windows runtime lock pins schema validation and its dependencies by
wheel hash; no runtime dependency download is needed.

Before promotion from preview, collect and independently compare representative
exports from each supported exporter/version: board extents, layer order and
materials, copper area including negative artwork/custom symbols, drills and
plating, component/pin/net counts, bottom-side transforms, and model assignment.
No Altium/OrCAD/Allegro/EAGLE/Zuken/Xpedition vendor corpus has been qualified by
the synthetic fixtures in this change.

The 2026-09-20 Marble v1.4.4 evaluation is a concrete scale check, not general
ODB++ qualification. Its final JSON-lines import worker frame was 265,181,020 bytes,
below the 256 MiB desktop limit. It imported 45 matrix layers (12 copper), 1,374
nets, 37,379 tracks, 122 zones, 7,246 pads, 3,664 vias, 3,871 drill records, and
994 components. Common rounded-rectangle copper flashes were normalized and no
copper-feature or EDA-reference error remained. The report still contained
1,118 unsupported technical-artwork warnings. Of 3,871 drills, 3,664 match vias
and 188 component holes match an exact `TOP` subnet and copper pad; the remaining
19 non-plated mechanical holes have no EDA owner reference and remain explicitly
unresolved. A drill-layer filename alone is not treated as proof of ownership or
plating. These results do not prove
support for every ODB++ symbol, polarity, step-repeat construct, exporter, or
physical stackup.

The corresponding normalized Marble project package measured 95,943,327 bytes.
Its compact reopen worker frame measured 245,974,230 bytes and retained all 122
canonical zones. Canonical `design/design-ir.json` members have a separate
512 MiB verified limit; other control-plane JSON members retain the 64 MiB cap.
