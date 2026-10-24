<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0135: Explicit sampled-network resistor heat to retained creeping CHT

Date: 2026-10-23. Status: accepted for experimental source-only development.

## Decision

Compose the existing exact-sample AC owner and retained tetrahedral creeping
CHT owner in `em_network_resistor_cht.py`. Require every external series resistor
to map to explicit solid-cell fractions or outside the thermal domain. Select
one exact frequency case; do not sum unrelated sweep cases. Do not infer EM-body
heat from a power deficit. Source identity remains caller-declared, not
authenticated geometry or a measured/calibrated material model.

Private mesh-admission reuse is additive in the CHT owner. It consumes only the
existing same-object, canonical-digest-bound internal ticket; external JSON
cannot supply one. It avoids repeating full retained-mesh admission while the
distinct fluid subset is still admitted and all child solver gates remain.

No new language, dependency, numerical kernel, worker route, native ABI, desktop
control or production capability is added. Python owns composition; existing
numerical owners retain their implementation and verification responsibilities.

## Consequences

This provides a runnable source-development loss/heat/flow example for supplied
PI/SI/EM networks, not general PCB extraction or live SPICE feedback. Explicit
retained-volume ownership is mandatory. Temperature-dependent resistance,
transient heat, thermal feedback, inertia, turbulence, distributed operation and
packaged/release qualification remain separate. See the
[method and executed evidence](../validation/AC_NETWORK_CHT_20261023.md).
