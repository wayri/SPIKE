# Manufacturer library qualification status

## Dedicated real-product browser

Open **Libraries → Manufacturer library** or the generic workbench's
**Manufacturer library** button. The window opens on real-product discovery,
not a parameter grid of generic presets.

The dated catalog contains 208 sourced product identities across 19
manufacturers: ADI, TI, Infineon, MPS, Wolfspeed/Cree, Vishay, Nordic, Arduino,
Microchip/legacy Atmel, Littelfuse, ST, Allegro, NXP, Renesas, Lattice, onsemi,
Nexperia and ROHM.
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

## 2026-10-20 source-provenance expansion

The 100 records dated `2026-10-20` were checked against official manufacturer
product pages, datasheets or product-selector tables. Each record retains the
official URL and independently authored category/description fact metadata.
The source supports the product identity and the narrow description only. It
does not establish current stock, lifecycle suitability, package interchange,
pin compatibility, electrical-model availability or simulation accuracy.

| Manufacturer | Added | Official source basis |
| --- | ---: | --- |
| Analog Devices | 7 | [Product pages and data sheets](https://www.analog.com/en/products.html) |
| Texas Instruments | 7 | [Product pages and data sheets](https://www.ti.com/product-category/overview.html) |
| Monolithic Power Systems | 5 | [Power product pages and selector tables](https://www.monolithicpower.com/en/products.html) |
| Infineon | 6 | [Part pages and data sheets](https://www.infineon.com/products) |
| STMicroelectronics | 7 | [Product pages and data sheets](https://www.st.com/content/st_com/en/products.html) |
| onsemi | 7 | [Official data sheets](https://www.onsemi.com/design/resources/technical-documentation) |
| Nexperia | 7 | [Product pages and product tables](https://www.nexperia.com/products) |
| NXP Semiconductors | 6 | [Product pages and family tables](https://www.nxp.com/products) |
| Renesas | 6 | [Product pages and selectors](https://www.renesas.com/en/products) |
| Microchip | 7 | [Product pages and data sheets](https://www.microchip.com/en-us/products) |
| Nordic Semiconductor | 5 | [Product pages and product guide](https://www.nordicsemi.com/Products) |
| Allegro MicroSystems | 5 | [Product pages and selection guides](https://www.allegromicro.com/en/products) |
| Wolfspeed | 5 | [SiC and RF product tables](https://www.wolfspeed.com/products/) |
| ROHM Semiconductor | 7 | [Product pages and data sheets](https://www.rohm.com/products) |
| Vishay | 6 | [Product pages and data sheets](https://www.vishay.com/en/products/) |
| Littelfuse | 7 | [Protection product pages and selection tables](https://www.littelfuse.com/products) |

No vendor SPICE, IBIS, firmware, encrypted model, or other executable payload
was downloaded or redistributed. All 100 additions are `model_not_reviewed`.
An official page mentioning a model does not change that state. A future model
intake must separately establish license, exact device/package/pin applicability,
parser and dependency compatibility, numerical behavior and qualification
evidence before execution can be enabled.

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
