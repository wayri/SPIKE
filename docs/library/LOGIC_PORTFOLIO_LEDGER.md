<!-- SPDX-License-Identifier: Apache-2.0 -->
# 54/74 logic portfolio ledger

Snapshot date: 2026-10-13

## Scope and counting rules

This ledger defines a bounded functional-model increment, not a claim to the
unbounded historical "74xx" universe. The bounded source set is the HC device
families listed below in official Texas Instruments or Nexperia documentation.
Other logic technologies (TTL, LS, ALS, AS, F, HCT, AHCT, AHC, AC, LVC, AUP,
ABT, CBT and vendor-specific derivatives), automotive suffixes, radiation
grades, obsolete devices and package/orderable suffixes are outside this
increment unless a row explicitly says otherwise.

Counts have three independent units:

- **Distinct executable device family**: one materially different packaged
  Boolean function and channel arrangement. SN54/SN74 names do not double this
  count, nor do package and orderable suffixes.
- **Documented series family name**: an SN54, SN74, CD74 or Nexperia 74 family
  name explicitly present in the cited manufacturer source. This is not an
  orderable MPN count.
- **Package/orderable variant**: an exact purchasable suffix such as
  `SN74HC138N` or `SN74HC138PWR`. This module records zero such variants and
  must not be used as an exact-MPN inventory.

The implemented counts are therefore:

| Measure | Count |
| --- | ---: |
| Distinct executable HC device-family functions | 20 |
| Additional executable generic sequential cores | 3 |
| Review-only exact device families | 5 |
| Executable rows with a documented 54-family name | 16 |
| Executable rows with a documented 74-family name | 20 |
| Exact package/orderable variants claimed | 0 |

The requested aspiration of 100 entries per category is not met by this
bounded increment. Inflating the count with SN54/SN74 aliases, package suffixes
or random historical numbers would not create additional models.

## Executable device-family functions

All executable rows have `model_status=generic_functional_unqualified` and
`backend=python.spikes.digital.DigitalKernel`. They compile to the existing
four-state `buf/not/and/or/xor/nand/nor/tristate/dff` primitives. There is no
C++ digital kernel in the checked-in SPIKE tree as of the snapshot date, and
this module does not add one or implement a parallel Python truth evaluator.

VCC and GND remain declared pins only. Delays are caller-selected per composed
primitive; they are not datasheet propagation delays. The source links support
function and recorded pinout facts only, not the implementation, electrical
parameters, timing qualification, package availability or equivalence across
manufacturers.

| Model ID | Distinct function | Documented family names | Source |
| --- | --- | --- | --- |
| `HC00` | Quad 2-input NAND | SN54HC00, SN74HC00 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc00.pdf) |
| `HC02` | Quad 2-input NOR | SN54HC02, SN74HC02 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc02.pdf) |
| `HC04` | Hex inverter | SN54HC04, SN74HC04 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc04.pdf) |
| `HC08` | Quad 2-input AND | SN54HC08, SN74HC08 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc08.pdf) |
| `HC10` | Triple 3-input NAND | SN54HC10, SN74HC10 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc10.pdf) |
| `HC11` | Triple 3-input AND | SN54HC11, SN74HC11 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc11.pdf) |
| `HC20` | Dual 4-input NAND | SN54HC20, SN74HC20 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc20.pdf) |
| `HC21` | Dual 4-input AND | SN54HC21, SN74HC21 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc21.pdf) |
| `HC32` | Quad 2-input OR | SN54HC32, SN74HC32 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc32.pdf) |
| `HC86` | Quad 2-input XOR | SN54HC86, SN74HC86 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc86.pdf) |
| `HC125` | Quad tri-state buffer, active-low enables | Nexperia 74HC125 | [Nexperia](https://assets.nexperia.com/documents/data-sheet/74HC_HCT125.pdf) |
| `HC126` | Quad tri-state buffer, active-high enables | Nexperia 74HC126 | [Nexperia](https://assets.nexperia.com/documents/data-sheet/74HC_HCT126.pdf) |
| `HC138` | 3-to-8 decoder, active-low outputs | SN54HC138, SN74HC138 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc138.pdf) |
| `HC139` | Dual 2-to-4 decoder, active-low outputs | SN54HC139, SN74HC139 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc139.pdf) |
| `HC151` | 8-to-1 mux with complementary outputs | Nexperia 74HC151 | [Nexperia](https://assets.nexperia.com/documents/data-sheet/74HC_HCT151.pdf) |
| `HC153` | Dual 4-to-1 mux with separate strobes | SN54HC153, SN74HC153 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc153.pdf) |
| `HC157` | Quad 2-to-1 mux with common strobe | SN54HC157, SN74HC157 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc157.pdf) |
| `HC283` | 4-bit binary full adder | CD74HC283 | [TI](https://www.ti.com/lit/ds/symlink/cd74hc283.pdf) |
| `HC688` | 8-bit identity comparator with enable | SN54HC688, SN74HC688 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc688.pdf) |
| `HC245` | Octal bidirectional tri-state transceiver | SN54HC245, SN74HC245 | [TI](https://www.ti.com/lit/ds/symlink/sn74hc245.pdf) |

The gate pinouts are shared with and generated from
`python/spikes/standard_logic.py`. The new 14-, 16- and 20-pin maps are
explicit in each descriptor. The mappings deliberately stop at the documented
through-hole/small-outline functional numbering and do not infer LCCC pinouts.

## Generic executable sequential cores

These three cores exercise actual existing `dff` primitives and are counted
separately from packaged HC devices. Their positional interfaces are not
physical package pinouts and do not claim exact-part equivalence.

| Model ID | Behavior | Boundary |
| --- | --- | --- |
| `CORE_DFF` | Positive-edge D flip-flop | No preset, clear, Q-bar or timing checks |
| `CORE_SIPO8` | Eight-stage serial-in/parallel-out shift core | No asynchronous master reset |
| `CORE_COUNTER4_SYNC` | Four-bit synchronous loadable enabled up-counter | No named-part reset or ripple-carry contract |

## Review-only exact functions

`bind()` raises `UnsupportedLogicModelError` for these rows. They remain in the
catalog so callers can present an exact unavailable state instead of silently
substituting a different behavior.

| Model ID | Referenced function | Blocking semantic gap | Source |
| --- | --- | --- | --- |
| `HC74_FULL` | Dual positive-edge DFF | Asynchronous preset/clear and complementary output | [TI](https://www.ti.com/lit/ds/symlink/sn74hc74.pdf) |
| `HC161_FULL` | Presettable synchronous counter | Reviewed clear/load/enable/ripple-carry contract | [TI](https://www.ti.com/lit/ds/symlink/sn74hc161.pdf) |
| `HC164_FULL` | SIPO register | Asynchronous master reset | [Nexperia](https://assets.nexperia.com/documents/data-sheet/74HC_HCT164.pdf) |
| `HC373_FULL` | Octal transparent latch | Transparent-latch primitive | [TI](https://www.ti.com/lit/ds/symlink/sn74hc373.pdf) |
| `HC595_FULL` | Shift register plus storage register | Direct asynchronous shift-register clear | [TI](https://www.ti.com/lit/ds/symlink/sn74hc595.pdf) |

## Verification and remaining closure

`tests/python/test_spikes_logic_portfolio.py` covers every gate truth table,
both tri-state enable polarities, decoder selection, mux selection, exhaustive
4-bit addition, equality comparison, both transceiver directions, DFF/shift/
counter sequences, catalog mutation isolation, unsupported exact-family
errors and bind preflight atomicity.

This establishes deterministic functional behavior only. It does not establish
manufacturer timing/electrical qualification, a native C++ runtime, mixed-
signal behavior, HDL equivalence, safety qualification, or complete 54/74
coverage. Closing the next sequential tranche requires reviewed asynchronous
set/reset and transparent-latch semantics in the owning digital kernel, then
package-specific sequence tests. Exact-MPN library adoption also requires a
separate orderable-part record with lifecycle and package evidence; these
family descriptors are intentionally ineligible for that count.
