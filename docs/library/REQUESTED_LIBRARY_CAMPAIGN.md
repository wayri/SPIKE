# Requested active-part library campaign

Assessment: 2026-10-13. This is an incremental implementation, not completion of
the full 54/74 portfolio or 100 qualified models per requested active category.

## Delivered models and execution

- `python/spikes/logic_portfolio.py`: 20 distinct package-family functional
  models, three separately counted generic sequential cores, five review-only
  families. Physical pin labels and power declarations are retained. Its
  `bind()` API explicitly uses the Python reference kernel; it does not silently
  invoke the native kernel.
- `src/spikes/digital_kernel.hpp`: owned C++20 four-state discrete-event SDK.
  Stable transport events, driver conflict resolution, positive-edge DFFs,
  bounded capture, resource/tick checks and fail-closed convergence handling.
  No HDL parser, Python bridge, analog coupling, physical timing qualification
  or shared-instance thread-safety is established.
- `scripts/build_spikes_logic_native_test.py`: generates native primitive
  graphs and 902 independent test vectors for the 20 functional models. The
  generator never compiles or executes code. Its manifest remains
  `generated_not_executed`; compiler/run evidence is separate.
- `spikes_studio.compiled_part_models`: original C++ sampled voltage-mode PWM
  and latched supervisor. PWM includes soft-start, PI anti-windup, UVLO,
  cycle-current limiting and thermal hysteresis. Supervisor includes supply
  qualification, sensed-voltage hysteresis, debounce and resettable fault latch.
  These are generic models, not equivalents of any manufacturer IC.

The compiled models require explicit code trust and an execution-mode choice.
Initialize driven independent voltage sources to zero for safe startup; their
initial values apply before the first accepted sample. Ground unused temperature
inputs. Sensor scaling, controller step and output holds are explicit; no
hard-real-time, hostile-code sandbox or continuous semiconductor-physics claim
is made.

## Portable snapshot

Run from the repository:

```text
python scripts/build_spikes_requested_library.py --output NEW_DIRECTORY
```

An existing output directory is rejected. The output contains hashed inventory,
logic descriptors, separate manufacturer-acquisition metadata, a `.spkctl`
sampled library, and resolved controller JSON files. Load the resolved controller
files through the existing controller configuration workflow. Importing files
does not compile or execute them. For programmatic parameter changes use
`compiled_part_models.configuration()`; do not edit generated source literals
as a substitute for model parameter validation.

The checked-in tranche is `artifacts/requested-library-20261013/manifest.json`.
It expressly records incomplete portfolio status. It is not a bundle of licensed
manufacturer SPICE implementations.

## Manufacturer acquisition and remaining gates

`manufacturer_model_catalog.py` contains 133 unique exact-MPN records. Categories
overlap: NPN is also BJT, NMOS is also MOSFET, and Schottky is also diode.
Summing category counts therefore does not count unique parts. Discovery records
do not count as executable models or qualification. See
[manufacturer acquisition](MANUFACTURER_MODEL_ACQUISITION.md) and
[logic coverage](LOGIC_PORTFOLIO_LEDGER.md).

The remaining work is substantial: complete historical/current 54/74 scope,
asynchronous/latch semantics, electrical power coupling and timing; obtain
manufacturer model payloads and redistribution rights; normalize dependencies
and dialects; qualify numerical execution and operating ranges; and reach 100
distinct evidenced variants per requested category. A MESFET/PIN-diode review
record is not admission of its model. Generic compiled controllers do not close
manufacturer PWM/controller coverage.

Local evaluation has also executed official TI LM358 and LM741 models through
explicit ngspice routing. LM358 requires the PSpice compatibility setting.
This establishes a bounded smoke run, not datasheet qualification. Vendor
payloads remain ignored local evidence and are excluded from the portable
snapshot pending redistribution/commercial-use rights review. See
[first manufacturer execution review](MANUFACTURER_FIRST_EXECUTION_REVIEW.md).

Numerical code still requires knowledgeable human review before release.
