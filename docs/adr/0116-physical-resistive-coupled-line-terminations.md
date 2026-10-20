<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0116: physical resistive source/load boundaries for supplied coupled lines

Status: accepted for experimental development, 20 October 2026.

The supplied coupled pair previously required incident waves. Useful loaded SI
needs explicit physical source/load boundary equations while retaining distributed
fields and a conservative electrical-to-thermal bookkeeping boundary.

Add a sampled physical-port Thevenin wrapper using conditioned four-port wave
feedback and the unchanged coupled-pair solver. Separate signed source work,
terminal resistor heat and distributed conductor/dielectric heat. Retain complete
child provenance and verify field/loss splits against modal constituents.

No PDE kernel, dependency or language is added. The independent physical spatial
boundary oracle verifies the feedback; no arbitrary geometry, nonlinear/reactive
endpoint or inferred thermal allocation is introduced. See
[method, references and limits](../RLGC_TERMINATED_PAIR.md).
