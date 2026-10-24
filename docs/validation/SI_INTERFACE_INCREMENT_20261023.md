<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI interface increment: 23 October 2026

This increment starts the [broader SI workflow plan](../SI_INTERFACE_EXPANSION.md).
It does not complete commercial-tool parity or protocol qualification.
The owner requires current released generation targets, with explicit draft and
legacy separation; current standards metadata is recorded in that plan, not
presented as implemented electrical limits.

## Implemented and checked

- Dedicated LPDDR, parallel DPI, USB 3.x and USB4-v2 PAM3 setup entries, preserving
  existing suite identifiers and a separate DisplayPort entry. PAM3 is admitted
  as declared vocabulary but numerical execution is rejected before lane/field
  allocation. Caller-provided capability names cannot override this block.
- Non-executing AMI scalar parameter/package inventory, supplied-byte hashes,
  strict bounds, public request schema and worker routes. No supplied binary is
  loaded, and ABI/execution admission remains false. Independent review found
  and repaired resolver-dependent parameter and malformed-container defects.
- C++20 transition-PI CDR reference with strict-FP main CMake/CTest targets,
  independent hand/analytical cases, binary64 gate-edge tests and owned-Python
  parity. Coincident threshold-touch crossings retain ambiguity rather than
  being rejected or deduplicated. No production binding is enabled.

Executed checks:

| Check | Result / local evidence |
| --- | --- |
| Combined AMI/parser/worker/protocol/PAM3/CDR Python regression | 54 passed, zero skips; build/si-expansion-focused-20261023.log |
| AMI request schema and existing schema catalog | 18 passed, zero skips; build/si-ami-schema-registration-r2-20261023.log |
| Frontend protocol registry, shared control standard, TypeScript | Passed; no native visual acceptance claimed |
| Main CMake Release CDR target + CTest | 1/1 passed; build/si-main-cmake-final-ctest-20261023.log |
| Independent/owned-Python native recurrence parity | Passed, including duplicate crossings; build/si-transition-pi-cdr-accepted-20261023.json |
| Architecture boundary check | Passed |
| Affected active parity receipts | 27 genuine canonical replays, 321 passed with zero skips; prior evidence retained |

The accepted benchmark report binds sources before/after, compiler/strict flags,
CPU, executable hash and all measurements. One warm-up and five measured runs
gave median recurrence times of 0.0247 ms / 1.028 ms / 2.2767 ms at
1,000 / 30,000 / 65,000 symbols. These exclude voltage crossing detection,
interpolation, ABI/process overhead and complete SI analysis. They are not an
end-to-end speedup or cluster-scaling claim. The test data are original synthetic
arrays and inert model bytes, with no KiCad or board input.

## Still required

Executable sandboxed AMI lifecycle and approved vendor-model association;
complete nonlinear IBIS; verified PAM3 and protocol-specific receivers/training;
clock-relative bus setup/hold and simultaneous-switching analysis; general
geometry/return/via/package extraction; independent and measured correlation;
production native binding and end-to-end performance evidence. Research-access,
normative-limit rights, human numerical review and release gates remain intact.

These source changes were made after the earlier preview installers were built.
Those installers must not be represented as containing this increment. A fresh
coherent full-suite/frozen/installer qualification is still required; the prior
failed diagnostic full run is not converted into a pass by focused checks.
