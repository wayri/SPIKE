# Manufacturer model library

The manufacturer library is separate from the generic parameter preset catalog.
Open **Manufacturer library**, import the manufacturer's plain-text SPICE file,
then enter the manufacturer, exact part number and official HTTPS download page.
The review shelf is saved in the project and supports project undo. Search it by
manufacturer, part number or declared subcircuit. Its inspector shows declared
pin order, dependencies, element inventory and constructs requiring review.

Intake never loads include files, evaluates expressions or executes compiled
code. Review records are deliberately not circuit-ready components. A filename
or manufacturer label cannot qualify a model. Original source is retained for
local review; check redistribution rights before sharing the project.

## Verified starting points

- [TI LM358](https://www.ti.com/product/LM358): jelly-bean dual op amp.
- [TI LM393](https://www.ti.com/product/LM393): comparator.
- [TI TL431](https://www.ti.com/product/TL431): adjustable reference.
- [TI OPA197](https://www.ti.com/product/OPA197): precision analog.
- [TI SN74HC14](https://www.ti.com/product/SN74HC14): Schmitt-trigger digital logic.

Official product listings identify SPICE downloads for these parts. They are not
bundled or approved for SPIKES execution.

## Actual LM358 inspection, 2026-09-06

The official SNOM268 archive was read in memory; no vendor source is distributed.
Archive SHA-256: `d3b7b2089c35518ab9f0f05290cf7856297e2680a40b0a731640923203a6dcc2`.
Member `lmx58_lm2904.lib` SHA-256:
`467a3e573420d1f5a21fab57b76be0e13073e854f609a73459a191958e314726`.

The model declares IN+, IN-, VCC, VEE, OUT. These are macro-model terminals,
not the complete physical dual-amplifier package pin numbering. The source uses
nested model definitions, behavioral VALUE/TABLE sources and noise constructs.
A unity-gain follower test deck was submitted to SPIKES' actual parser. It failed
with `.model cards are supported only at top level in this bounded slice.`
Simulation was therefore not attempted. A generic op amp is not substituted.

Remaining: parser and device support, electrical pin/package mapping, reviewed
licensing, DC/AC/transient and limits qualification, equal-model reference-engine
tests, and then promotion into the executable component library.
