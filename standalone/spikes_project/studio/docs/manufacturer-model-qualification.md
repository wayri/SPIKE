# Manufacturer models: release gate

The current catalog contains 5,000 generic parameter presets from 100 archetypes,
including 650 native recipes. It contains **zero qualified manufacturer models**.
The 4,350 equation-bench presets cannot be connected to circuit MNA. Counts must
never be presented as distinct branded devices or complete circuit-model coverage.

Use **Circuit-ready parts** in the browser to exclude equation benches. The
separate **Manufacturer model sources** directory identifies sources awaiting
qualification; it does not insert models or silently replace them with generic
approximations. Search supports `manufacturer:`, `qualification:` and `fidelity:`.

## First intake candidate: TI LM358

Checked on 2026-09-06: the [official LM358 product page](https://www.ti.com/product/LM358)
lists **LMx58_LM2904 PSpice Model (Rev. C)**, package SNOM268C, and separate
TINA-TI resources. The [official model download](https://www.ti.com/lit/zip/SNOM268)
is a ZIP archive. This is source discovery only: archive contents, archive-specific
license, dependencies and compatibility have not been reviewed here. No model
code has been bundled or qualified. A download link is not redistribution consent.
The product page describes multiple revisions; LM358 and LM358B are not interchangeable
parameter identities. The exact downloaded model identity must be recorded.

## Required acceptance evidence per manufacturer item

1. Manufacturer, exact orderable family/version, source URL, archive SHA-256,
   retrieval date, source-file hashes, license and redistribution decision.
2. Exact model/subcircuit names and electrical pin order, including supply pins;
   map symbol units to the model rather than inferring pins from a drawing.
3. Syntax/dependency inventory and successful native parser and execution tests.
   Missing device or expression support is a blocker, not permission to simplify.
4. DC transfer, bias/current, common-mode range and output swing tests; AC gain,
   bandwidth and phase; transient slew, overload recovery and startup tests.
5. Equal-model reference-engine results with solver tolerances and decks retained;
   comparison with applicable datasheet curves and stated test conditions.
6. Document features the supplied model omits: thermal behavior, noise, protection,
   package parasitics and statistical mismatch are not implied by a product name.

The present vendor intake preserves supplied source and reports declarations;
it is **not** a compiler, validation runner or execution approval. Current native
device coverage is insufficient to promise arbitrary vendor op-amp compatibility.
Native imported-part insertion must remain gated until these checks pass.
