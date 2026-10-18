# Manufacturer library qualification status

## Dedicated real-product browser

Open **Libraries → Manufacturer library** or the generic workbench's
**Manufacturer library** button. The window opens on real-product discovery,
not a parameter grid of generic presets.

The dated catalog contains 108 sourced product identities across 16
manufacturers: ADI, TI, Infineon, MPS, Wolfspeed/Cree, Vishay, Nordic, Arduino,
Microchip/legacy Atmel, Littelfuse, ST, Allegro, NXP, Renesas and Lattice.
It is not an exhaustive ordering-code portfolio. Use manufacturer/category
filters, fuzzy search, sortable headings, symbols and official source links.
Search aliases include ADI, TI, MPS, Cree and nRF. Lattice entries do not
supply a bitstream emulator or an electrical package model.

**Sourced electrical parts** retains exact-package pin/rating records and
explicit ideal-nominal passive insertion, not manufacturer dynamic models.
**Project model review shelf** retains imported source and provenance without
approving execution.

## Local LTspice library

Choose the installed application's `lib` directory in **Local LTspice**.
The bounded background index records declarations, symbol metadata, explicit
symbol dependencies, original paths and raw-file SHA-256 hashes. No includes,
DLLs or model code execute. Model bodies are not embedded in the index or
redistributed. Export/open metadata indexes for reuse; source hashes are
checked again before review/import.
Opening an exported index asks you to confirm the actual library folder;
an imported metadata file cannot silently choose its own filesystem/network root.

Declaration counts include helper models, not distinct qualified parts. Scan
diagnostics expose skipped formats and limits. The first 2,000 matching
declarations are displayed; refine search for more. Exact-name product links
do not infer package identity, pin equivalence or qualification.

**Review original source** opens the actual local file read-only. **Place
intrinsic model** imports one unchanged `.MODEL` card with its continuations,
requires usage-rights confirmation and uses the existing model editor/native
parser before an undoable insertion. Unsupported types and parameters are
rejected, not discarded to manufacture compatibility. Subcircuits require
separate dependency/pin review; helpers are not silently selected or flattened.
Sharing a circuit with an imported card embeds vendor source: review its
terms separately. Encrypted and LTspice-specific models are not universally
compatible merely because their files can be indexed.

Contracts: `spikes/manufacturer-discovery/v1` and
`spikes/ltspice-local-library/v1`. Broad executable manufacturer-model
qualification remains incomplete.

The project-local manufacturer shelf is an import/review workflow, not a
prequalified executable parts catalog. It retains user-supplied source,
provenance, pin declarations, dependency inventory and hashes. No vendor model
payload is bundled by this workflow. Review redistribution terms before sharing
a project that embeds manufacturer source.

The prior inspection of the [official TI LM358 model](https://www.ti.com/product/LM358)
recorded failure at a model declaration inside a subcircuit. Scoped static diode
models are now implemented and tested, so that historical error is not a current
blanket restriction. The complete LM358 archive has not been requalified: its
other model types and behavioral expressions require additional implementation.
It must remain not-qualified rather than be replaced with a renamed generic part.

See [model review checklist](manufacturer-model-qualification.md),
[open collection assessment](OPEN_MODEL_COLLECTIONS.md), and
[two-stage execution record](TWO_STAGE_SPICE_EXECUTION.md).
