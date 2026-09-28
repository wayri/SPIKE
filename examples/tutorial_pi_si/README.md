<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->

# PI/SI casebook inputs

`straight_trace.design.json` is an original synthetic DesignIR fixture owned
by SigHarmonic and released under Apache 2.0. It is not a copied PCB or measured
material dataset. Copper dimensions and conductivity are explicit so the DC
result can be checked against `R = length/(sigma * width * thickness)`.

The casebook also uses the original SPIKE-owned
`examples/si/analytical-coupled-rlgc.json` (MIT, SigHarmonic): a deliberately
synthetic four-port RLGC channel with illustrative coupling values. It is not
derived from Marble or any measured board. The existing
`examples/si/10g-nrz-cdr.json` is likewise an ideal numerical fixture, not an
Ethernet compliance pattern.

Screenshots and exact run commands are in `docs/PI_SI_WORKED_CASEBOOK.md`.
