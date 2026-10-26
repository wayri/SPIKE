<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# SI execution increment - 23 October 2026

## Delivered behavior and boundary

The [trusted native AMI host](../SI_AMI_EXECUTION.md) executes actual Init,
ordered GetWave blocks and Close in a disposable C++20 child. Windows x64,
explicitly reviewed native code, system-only imports and the existing OS Job
Object supervisor are admitted. It is not a security sandbox or a complete
IBIS/Vendor/AMI-generation qualification. The main JSON worker cannot load a
model DLL. The optional root CMake target `SPIKE_BUILD_AMI_HOST=ON` built with
MSVC 19.51 and strict floating point. Its actual identity-model call passed;
host SHA-256 is `1a405599888ec026c838fbe4fc6ffc8d418c917fdc2d132f4ed633ff25a22b7a`.

The [generic PAM3 owner](../SI_PAM3.md) now executes explicit three-level
stimuli, sampled voltage FIR convolution, two fixed-threshold eyes and SER.
Worker method `simulate_si_pam3` has a strict registered JSON contract and
request digest. [The executable example](../../examples/si/pam3-generic-worker.json)
is original synthetic data, not USB4 traffic. NumPy/SciPy compiled FFT and
probability kernels are reused instead of duplicating them in another language.
This does not implement USB4 encoding/training, physical CDR, FEC or current
generation-specific electrical acceptance limits. Existing protocol gates remain.

## Review feedback implemented

- Direct Gaussian survival functions replace subtracting a near-one CDF. For
  balanced identity levels -1/0/1 V, midpoint thresholds and sigma=0.05 V, the
  conditional SER matches the independent erfc oracle near
  `1.0159804032214e-23`, with a relative-tolerance assertion rather than an
  absolute tolerance that would accept zero.
- Full bounded AMI output-tree syntax replaces a root-prefix regex. Actual
  malformed Init/GetWave fixtures now fail; strings remain model-owned and are
  copied before subsequent calls and Close.
- Physical AMI Init tests use `1/dt` impulse amplitude at three sample intervals
  and check integrated gain/area. These continuous-time 1/s samples are distinct
  from dimensionless discrete FIR coefficients in the PAM3 API.
- Required PAM3 scalar JSON fields reject numeric strings, like optional
  controls. Unknown fields cannot request native execution or self-promote status.
- Worker qualification now compares every packaged JSON schema with current
  source bytes. Missing, modified and extra schema payloads fail. An initial
  candidate captured an earlier catalog; it is retained as historical evidence,
  not the final coherent candidate.

## Executed checks

`build/si-execution-focused-20261023.log` records 118 passing tests, zero skips,
including actual native AMI lifecycle/failure/crash/timeout/cancel/state/clock
cases, PAM3 analytical FIR/delay/noise/tail/resource tests, fresh worker tests,
inventory/schema tests, existing channel/workflow and board-fixture integrity.
The later numeric-string regression and schema-coherence checks are rerun
separately and recorded with final candidate evidence. The native CDR CTest
target passed 1/1. Independent review verified corrected AMI output rejection
and physical impulse checks; human numerical/security release review is separate.

All 27 affected SI parity stages were genuinely replayed unchanged: 321 passed,
zero failures/skips; receipt/log pairs end `-si-execution-20261023`. The backlog
validator passed with 50/90 stages done and the post-parity gate still closed.
Passing those receipts does not close the 67 pending capability benchmark
definitions or the full-suite release gate.

`scripts/benchmark_si_pam3.py` uses a warm-up and five measured runs, source
identities before/after, explicit CPU/runtime/thread data and analytical
identity-eye checks. It measures in-process request-to-result work, not board
extraction, IPC, native AMI execution, end-to-end SI or cluster scaling.

## Actual Marble and White Rabbit attempts

`scripts/verify_si_real_boards.py` imports the complete pinned boards, binds
source identities and tries both strict and piecewise channel admission.
`build/si-real-board-admission-r2-20261023.json` contains the actual results:

| Board | Imported objects | Numerical admission |
|---|---|---|
| Marble v1.4.4 | 37,380 tracks; 5,272 pads; 3,664 vias; 124 zones | Strict path rejected for bends. Piecewise path reaches physical-property admission: copper conductivity is unspecified in the imported material, so no resistance/eye is fabricated. |
| White Rabbit core converted fixture | 27,699 tracks; 6,860 arcs; 4,550 pads; 2,819 vias; 130 zones | Strict path rejected for bends. Piecewise path rejects ambiguous reference-zone ownership. Conversion losslessness is not established. |

These are diagnostic selected paths, with declared 50 ohm/DC-64 MHz inputs,
not asserted board operating conditions or generation limits. No geometry,
reference plane, material or device model was silently substituted. Board
import and fail-closed admission evidence is not successful channel extraction
or measured validation. Missing physical inputs and general multi-zone return
extraction remain real integration work.

## External models searched, not executed

The owner had no vendor models and authorized public-source research.
The official [IBIS test-kit collection](https://github.com/IBIS-Library/IBIS-AMI-test-kits)
provides legacy evaluation archives. Only filenames, README, binary headers
and license-file presence were inspected; no external source code, model
algorithm, test vector or prose was adapted. The Cadence 2011 kit's inspected
Windows binary is PE machine 0x014c (32-bit), incompatible with the admitted
64-bit host. Cached archive SHA-256:
`6809c433b914d019257755901db0f7b1b6fce2decfb8e46616b0b2899697b561`.

The public TI SPRM808 archive was fetched for inspection from
[TI's download endpoint](https://www.ti.com/lit/zip/sprm808).
It contains `SPRM808-1.0-windows-installer.exe`, not directly admitted model
members. The installer was not run and its terms/dependencies were not bypassed.
Archive SHA-256:
`a1ed6e1725c29b2ce435bd7369909bcd476c524e5f9abb7e8175fb4ce56b04f6`.
[ADI's model catalog](https://www.analog.com/en/resources/simulation-models/ibis-models.html)
also lists AMI downloads requiring a personal-details/consent form; no form
was submitted. Public availability is not execution or redistribution approval.
No external executable or archive is included in the release payload.

## Final source and frozen-worker evidence

- `build/si-execution-final-focused-20261023.log`: **120 passed, zero skips**,
  including the final strict scalar, native execution schema and packaged
  schema-coherence regressions.
- `build/si-execution-final-parity-20261023.log`: validator passed after the
  27 genuine unchanged replays (321 tests); no gate was waived.
- Native strict-FP Release CDR target: CTest 1/1 passed. Main CMake AMI host:
  compiled and executed the actual original identity fixture successfully.
- `build/si-pam3-benchmark-r2-20261023.json`: one warm-up plus five measured
  runs at 32 samples/UI; median 1.526 / 17.834 / 36.166 ms for
  1,024 / 8,192 / 16,384 symbols. Current sources are bound before/after.
- Coherent frozen worker:
  `build/si-execution-candidate-r3-20261023/resources/spike-worker/spike-worker.exe`,
  Windows x64, Python 3.12.9/PyInstaller 6.21.0, 19,328,575 bytes,
  SHA-256 `4a7b2798b3dcb07d6cd284848eda86aa0d5cbac2e1609f7cd4eeec044e6a4f69`.
  Its adjacent integrity manifest records 15/15 permanent benchmarks, 8/8
  source/frozen runtime comparisons, actual PAM3 identity/two-eye/rare-tail
  probes and all 261 JSON schemas equal to source.
- `build/si-execution-r3-source-match-20261023.json`: all 491 checked Python
  modules match current code, including constants/instructions/line tables;
  no changed, missing or required-missing module.
- Architecture check passed. No fresh full-repository suite, normal installer
  installation, GUI visual acceptance or Linux release qualification is claimed.

Earlier candidate directories/logs are retained; they are not the final
coherent candidate. The earlier desktop installers were not replaced. The
standalone native AMI host is separate from the frozen generic worker and is
not silently bundled as a generally executable model loader. The skill-driven
source/frozen/schema separation strengthened packaging checks; it did not
promote this worker evidence to installer or physical/protocol qualification.

## Still open

Vendor binary/license/dependency admission and actual interoperability;
Tx/channel/Rx composition, applicable nonlinear/clock/training behavior;
authorized exact-revision limits and independent compliance references;
real-board extraction/material/return closure and measured correlation;
current native/source parity, clean full suite, human numerical/security review,
Windows/Linux clean-machine installer/offline/upgrade/uninstall checks.
Neither a worker build nor synthetic ABI checks can close these gates.
