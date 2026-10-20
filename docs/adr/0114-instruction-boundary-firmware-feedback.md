<!-- SPDX-License-Identifier: Apache-2.0 -->
# 0114: Explicit instruction-boundary firmware feedback

Status: experimental engineering-preview boundary, 2026-10-20.

The existing timestamped software-write adapter runs a CPU interval ahead of
the plant with held inputs. Keep that mode and its provenance for existing
projects; never silently reinterpret a saved simulation.

A separate `synchronous` mode uses the reviewed native backend's blocking
one-instruction step. Before each instruction it injects receiver levels from
the accepted owned-C++ electrical solution; after the instruction it queues
captured output events and advances the plant to the instruction endpoint.
No Python electrical solver is introduced. Fixed internal hooks and bounded
monitor messages are not imported user scripts. Opening a project executes none
of these hooks; runtime/image hash approval remains required.

This removes the multi-instruction lookahead interval for admitted CPU GPIO
observations. It does not solve asynchronous receiver crossings inside an
instruction, analog metastability, MCU power consumption/brownout or board
propagation. Peripheral admission is explicit and requires its own execution
evidence, not merely an implemented register bank. An instruction grid is not
a hardware-cycle timing model. Physical SI/PI and real-time claims remain gated.

The initial scope uses the explicit 10 ns instruction lattice, 1..1000
instructions per report. Inputs in an unknown/unpowered state stop execution.
A failed plant step after CPU execution latches the combined session failed:
native plant checkpoint recovery alone must not resume irreversible firmware.
Users must restart both. Full emulator checkpoint coupling is future work.

One monitor round trip per instruction trades throughput for conservative
feedback. Work remains off the GUI thread. Reporting is bounded; a cooperative
worker control callback acknowledges pause/stop between completed instruction
and plant steps, never midway through a native instruction or solver call.

See [independent causal and bus numerical contract](../validation/BIDIRECTIONAL_GPIO_BUS_20261020.md)
for derivation, references, test requirements and limitations. Agent review and
synthetic verification do not replace knowledgeable human numerical review.
