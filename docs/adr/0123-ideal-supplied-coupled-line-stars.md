<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR0123: ideal branched supplied coupled lines

Status: accepted for experimental development,20 October2026.

Supplied coupled propagation previously covered chains. Add2..8 uniform coupled
legs meeting at two distinct ideal physical conductor nodes. Independently derive
J=2/m ones-I from equal voltage and KCL, then reuse the existing conditioned
block solve and unchanged actual pair field producers. Each leg retains its
strongly bound source/field/loss provenance and owns integrated pair heat once.

Expose a separate strict request/result contract through the RF worker and CLI.
Exterior ports follow leg/conductor order and use collision-free JSON-pair labels.
Raw node voltage/current/power residuals remain explicit; no junction heat,
contact area, mutual-term allocation or thermal cell is inferred. No new language,
dependency or native PDE kernel is added. General graphs, piecewise legs, RLC
star endpoints, geometric parasitics, transient/thermal/board qualification and
human release review remain separate gates. See
[method and sources](../RLGC_COUPLED_STAR.md).
