<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR0122: physical RLC endpoints for supplied coupled cascades

Status: accepted for experimental development,20 October2026.

Piecewise coupled channels previously accepted exterior incident waves. Compose
the verified S09 physical series-R/L and node-shunt-C endpoint closure with the
unchanged S10 section connection and actual field producer. Keep separate
conditioning checks for internal and endpoint feedback, bind every actual section
drive/field/heat split and reconstruct the complete canonical child ledger.

Expose strict separate request/result contracts through the RF worker and CLI.
Preserve named terminals/sections and separate heat W, mean energy J, reactive
var and signed source VA for later explicit multiphysics coupling. No new PDE,
constitutive model, language or dependency is introduced. General nonlinear,
transient, geometry/contact/thermal and board qualification remain separately
gated. See [method/source ledger](../RLGC_LOADED_CASCADE.md).
