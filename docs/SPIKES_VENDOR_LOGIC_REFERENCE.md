<!-- SPDX-License-Identifier: Apache-2.0 -->
# TI logic archive reference checks — 2026-10-12

Official [HC10](https://www.ti.com/product/SN74HC10) and
[HC11](https://www.ti.com/product/SN74HC11) pages supply behavioral electrical
SPICE archives SCLM227 and SCLM226. Original archives and intake inventories are
retained privately under `.tmp/spikes-active-model-intake-20261012`; they are not
bundled into an installer or an Apache-licensed library. Copyright notices remain
intact. Redistribution rights have not been established.

`scripts/qualify_spikes_logic_vendor.py` consumes those local archives, verifies
their exact hashes and expected single text member, and runs unmodified model
constructs in explicitly selected ngspice PSpice compatibility mode. Transport
line endings are normalized only. There is no silent SPIKES backend fallback.

Both models passed all eight three-input combinations at 5 V, 25 C and a 10 kohm
output load. High outputs must be 4.8–5.1 V and low outputs −0.1–0.2 V. Evidence:
`artifacts/spikes-vendor-logic-dc-20261012.json`, including model/member/engine
hashes and measured voltages. These broad DC pass limits establish truth-table
execution only, not precision agreement with the manufacturer's curves.

Each archive represents **one gate**, despite its package-family name. Its eight
subcircuits include helpers, not eight distinct ICs. A full physical package
wrapper requires reviewed gate mapping and shared-power consumption semantics.

Not qualified: propagation delay, edge response, supply or temperature ranges,
full-package power, noise, SI, native SPIKES execution, or measured hardware.
Manufacturer catalog placement remains disabled; an acquisition reference is
not an installed runnable part. These checks do not constitute endorsement or
release qualification.
