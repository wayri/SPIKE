# Manufacturer model acquisition catalog

## Status and boundary

`python/spikes/manufacturer_model_catalog.py` is a reproducible evidence
catalog for exact manufacturer part identifiers. It does not contain model
payloads, profile aliases, generated substitute MPNs, or executable library
entries. Every record has `runnable: false` and
`redistribution_approved: false`. Catalog presence is therefore not a claim
that SPIKE can simulate, redistribute, or qualify the part.

The source review was performed on 2026-10-13. It used primary manufacturer
product pages, selection guides, model listings, and model-license pages. The
catalog records the exact source URL and assessed date so a reviewer can repeat
the check. URLs can change after that date and must be reassessed before
acquisition.

## Record contract

`catalog()` returns isolated dictionaries with these integration fields:

- `id`, `manufacturer`, and exact `mpn` identify the evidence record.
- `categories` uses only `opamp`, `bjt`, `npn`, `pnp`, `mosfet`, `nmos`,
  `pmos`, `ganfet`, `sicfet`, `mesfet`, `pin_diode`, `diode`, `schottky`,
  `controller`, and `pwm`.
- `source` contains `url`, `accessed_on`, `document`, and the `fields` actually
  supported by that source.
- `model_readiness` distinguishes a catalog-only lead, a model pointer on a
  product page, an unreviewed direct download, and an unreviewed click-through
  download.
- `model_download_url` is present only for the six exact download targets that
  were directly identified during this review: LM358, LM741, TL072, OPA197,
  OPA2197, and AD811. A product page is not relabeled as a direct download.
- `required_backend`, `license_state`, `evidence_categories`, and `limitations`
  preserve unresolved execution, terms, and qualification work.

Category membership is deliberately overlapping. An NPN record has both `bjt`
and `npn`; a P-channel MOSFET has both `mosfet` and `pmos`; PIN and Schottky
records are also `diode` records. `coverage_summary()` counts unique records in
each category. Do not add category totals together and do not count NPN or PNP
as a disjoint second BJT population.

## Curated coverage and 100-record target

The checked-in tranche has 133 unique exact-MPN records and zero runnable
models. No category yet reaches the requested acquisition target of 100.

| Category | Exact records | Remaining to 100 |
| --- | ---: | ---: |
| opamp | 14 | 86 |
| bjt | 20 | 80 |
| npn | 10 | 90 |
| pnp | 10 | 90 |
| mosfet | 20 | 80 |
| nmos | 12 | 88 |
| pmos | 8 | 92 |
| ganfet | 18 | 82 |
| sicfet | 16 | 84 |
| mesfet | 4 | 96 |
| pin_diode | 9 | 91 |
| diode | 29 | 71 |
| schottky | 10 | 90 |
| controller | 12 | 88 |
| pwm | 12 | 88 |

The MESFET rows are not invented scarcity placeholders. They name real Qorvo
and MACOM RF products whose primary pages identify GaAs MESFET technology:
FH101-G, NBB-400, MAAM02350-A2, and MAAM37000-A1. They are catalog evidence
only. Their RF component scope and likely SPICE/S-parameter needs must be
reviewed before any circuit-model claim.

## Primary evidence sampled

The catalog stores the record-level URLs. The following sources establish the
main acquisition and licensing boundaries used to classify them:

- Texas Instruments product pages list manufacturer PSpice downloads for
  [LM358](https://www.ti.com/product/LM358),
  [LM741](https://www.ti.com/product/LM741), and
  [TL072](https://www.ti.com/product/TL072A). The pages point to TI evaluation
  item terms; those terms have not been approved for SPIKE redistribution.
- Analog Devices lists an AD811 SPICE macro model on the
  [AD811 product page](https://www.analog.com/en/products/ad811.html). Access
  redirects through the
  [ADI SPICE model license](https://www.analog.com/en/license/spice-models.html),
  which allows some redistribution but excludes third-party-origin models.
  Model origin therefore remains a required per-file review; the catalog does
  not infer permission from the vendor name.
- Nexperia's
  [DFN1006 MOSFET family page](https://www.nexperia.com/products/mosfets/family/dfn1006-mosfets)
  demonstrates per-MPN SPICE files, while its
  [2025 GaN selection guide](https://assets.nexperia.com/documents/selection-guide/Nexperia_Selection_Guide_2025.pdf)
  enumerates the GaN device identifiers used here. A family listing is not an
  acquired payload or solver-compatibility result.
- Infineon states that BAR-family PIN-diode models are exposed from individual
  product pages; [BAR64-02V](https://www.infineon.com/part/BAR64-02V) is the
  confirmed example. The
  [InfineonSpice manual](https://www.infineon.com/dgdl/Infineon-InfineonSpice_2025.01-UserManual-v01_00-EN.pdf)
  documents a vendor model-store workflow. Neither source grants SPIKE a
  redistribution right.
- ST documents multiple power-MOSFET model levels in
  [UM1575](https://www.st.com/resource/en/user_manual/dm00064632.pdf), and the
  [STPS0560Z product page](https://www.st.com/en/diodes-and-rectifiers/stps0560z.html)
  lists a Schottky PSpice library. Exact subcircuit presence and dialect remain
  acquisition-time checks.
- ROHM's
  [simulation model overview](https://fscdn.rohm.com/en/products/databook/applinote/common/overview_of_rohms_simulation_models_ic_discreet_an-e.pdf)
  distinguishes compact, macro, behavior, thermal, and encrypted model levels
  for transistors, diodes, Si MOSFETs, SiC, GaN, and ICs. That distinction is
  retained as unresolved backend review rather than flattened into "SPICE
  compatible."
- Wolfspeed exact SiC identities come from its
  [SiC power products catalog](https://assets.wolfspeed.com/uploads/2022/04/wolfspeed_power_line_card.pdf).
  Product identity does not establish that a model download exists for each
  row.
- Vishay exposes product-specific design-tool pages, for example
  [Si7326DN](https://www.vishay.com/en/product/74444/tab/designtools-ppg/),
  but a PDF model description is not assumed to be an executable subcircuit.
- MACOM product pages identify exact PIN-diode parts and, for selected parts,
  a simulation-model document; examples include
  [MADP-000907-14020P](https://www.macom.com/products/product-detail/MADP-000907-14020P)
  and [MA4P7493-134](https://www.macom.com/products/product-detail/MA4P7493-134).

## Readiness and license states

Current record states are:

| State | Records | What it supports |
| --- | ---: | --- |
| `catalog_only` | 108 | Exact identity/classification evidence only |
| `manufacturer_model_page_unreviewed` | 19 | Manufacturer page indicates a model pointer; no payload review |
| `manufacturer_download_unreviewed` | 5 | Direct TI download URL identified; no payload or terms approval |
| `manufacturer_clickthrough_unreviewed` | 1 | AD811 click-through target identified; no origin/terms approval |

These states are availability evidence, not capability maturity. A downloaded
file would still require immutable content identity, exact MPN and package
mapping, license/origin review, parser and dialect checks, named backend and
version, pin order, operating envelope, convergence/failure tests, and scoped
behavior validation. A checksum alone authenticates neither publisher nor
redistribution rights.

## Acquisition plan to reach 100 per category

For each category shortfall, acquire records in auditable batches of no more
than 25 exact MPNs from a primary manufacturer selector, selection guide, or
product-page export. Each batch must:

1. Preserve the exact manufacturer MPN and source revision or assessment date.
2. Record only fields visible in the cited source; do not infer model presence
   from adjacent family members.
3. Capture a direct model URL only when the manufacturer exposes that exact
   target. Keep login, agreement, and export-control gates explicit.
4. De-duplicate on normalized `(manufacturer, MPN)` and apply the overlapping
   category rules above.
5. Run `validate_catalog()` and the focused test before updating the count
   table. Do not replace real gaps with generated suffix permutations.

Prioritize the largest and most safety-relevant gaps as follows:

- PMOS, PIN-diode, NPN/PNP, Schottky, and PWM/controller: expand primary
  selectors from Nexperia, Infineon, ST, TI, ROHM, Vishay, and MACOM.
- Op amps: add exact common, precision, low-noise, high-speed, zero-drift, and
  high-voltage variants from TI and ADI while keeping family macro-model scope
  explicit.
- GaN and SiC: use vendor selection guides first, then verify per-device model
  pointers and backend restrictions. Do not assume a family archive contains
  every product listed in the selector.
- MESFET: search actual RF product databases under their own family terminology
  (GaAs MESFET transistor, MMIC, switch, or amplifier) and record device scope.
  If a target requires a discrete transistor rather than an MMIC, keep that
  acceptance rule separate instead of renaming another FET technology.

## User-provided model evidence

`propose_user_model_admission()` hashes an original local file in place and
returns an `unapproved` evidence record. It requires an exact MPN, canonical
categories, and at least one license-evidence reference. It rejects symlinks
and files above the bounded hashing limit. The helper does not copy, parse,
import, load, or execute the file and cannot promote it to runnable or
redistributable status. Human license and engineering review remain mandatory.

## Verification

Run the focused checks with:

```powershell
$env:PYTHONPATH = "python"
python -m unittest tests.python.test_spikes_manufacturer_model_catalog -v
python scripts/check_architecture.py
```

The unit test fixes the current category counts, verifies overlap semantics,
checks common and precision op-amp coverage, rejects placeholder MPNs and
readiness promotion, and proves that user evidence admission only hashes the
original file.
