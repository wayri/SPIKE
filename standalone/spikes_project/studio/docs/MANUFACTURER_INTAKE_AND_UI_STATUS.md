# Manufacturer intake and UI development — 8 September 2026

## Verified development changes (not installed in beta.6)

Ctrl+V on the schematic now recognizes a single MODEL card (including continuation
lines), reviews its SPICE pin order and creates one selected part in the current
sheet. Existing layout/source is retained. Duplicate model names receive a unique
suffix rather than replacing a model used by other parts. New nodes are isolated;
wire them before running. One undo reverses insertion. Text fields still receive
ordinary text paste, and full decks still use the existing circuit import flow.

Supported placement families are D, NPN, NMOS, BSIMBULK and BSIMCMG, subject to the
native parser's parameter support. Unknown/unsupported families are rejected, not
replaced with a different device. This is not complete vendor subcircuit-to-symbol
generation or a completed property/pin editor overhaul.

Plot context menus now expose expression insertion and numerical time/Y bounds,
alongside cursor readings/math, fit, pan/rectangle zoom, notes, grid and legends.
These additions do not establish LTspice/QSPICE plotting parity.

## Public manufacturer model collection

Use `scripts/collect_manufacturer_models.py --vendor ... --url ... --output ...`
for a discovered, explicit manufacturer HTTPS URL. It restricts hosts/redirects,
bounds download and decompression sizes, hashes original content and inventories
archives without extracting paths or executing models. Host registrations cover
13 manufacturers; this is an intake boundary, NOT a claim of downloaded catalogs
or native model compatibility.

TI's LM358-family SNOM268 revision C archive was downloaded from
https://www.ti.com/lit/zip/SNOM268 on 8 September 2026. It is retained under
`model-collections/manufacturer-intake/ti`, SHA-256
`d3b7b2089c35518ab9f0f05290cf7856297e2680a40b0a731640923203a6dcc2`.
There are 12 MODEL and 18 SUBCKT declarations including helpers, not 30 qualified
parts. It is not approved for redistribution or native execution.

ST's X02 page identifies the public `standard_sensitive_scr_pspice.zip` collection;
the attempted download timed out. Infineon public model guidance distinguishes
electrical and electrothermal model levels; some model downloads require login.
No gated access was bypassed.

## Qualification work still required

For each exact model/version: review license, identify primitive/grammar gaps,
verify pins and units, compare native results to a reference engine at equal
tolerances, and check against manufacturer curves over documented conditions.
IGBT checks include transfer/output curves, gate charge, tail current, switching
energy and temperature. SCR checks include trigger/latch/holding currents,
commutation, blocking, dv/dt and temperature. Missing effects must remain explicit.

Production IGBT/thyristor physics models, broad manufacturer qualification and the
major UI/workflow overhaul remain incomplete. The installed beta.6 is unchanged.
