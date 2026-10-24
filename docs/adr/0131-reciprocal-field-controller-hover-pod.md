<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0131: Reciprocal field/controller/hover-propeller benchmark

Date: 23 October 2026. Status: accepted experimental source implementation;
human numerical release review and installed-runtime qualification remain open.

The requested pod needs a genuine feedback loop. Existing prescribed-current
machine studies and the scalar co-simulation master do not establish terminal
flux/backEMF/torque reciprocity or propeller reaction. Add a separate bounded
worker contract instead of expanding or reinterpreting those legacy requests.

`propulsion_pod_field.py` owns normalized two-phase P1 winding ports and a fixed
linear recoil-PM field basis. `propulsion_pod_propeller.py` owns attached-flow
no-swirl annular hover BEM. `propulsion_pod.py` composes terminal, shaft and
propeller equations with exact harmonic discrete-gradient work. The existing
SPIKES persistent C controller owns sampled control execution. A fixed built-in
original C source is compiled only on explicit run; clients cannot inject code
through this contract. All controller/field/shaft/propeller states belong to
one run. Failure aborts the whole run; no partial result is reported completed.

Worker methods are `propulsion_pod_capabilities`, `validate_propulsion_pod` and
`run_propulsion_pod`; the last two take exactly `{request}`. Python Workspace
templates execute the same routes. Results have their own contract and are not
silently published as PCB AnalysisResults. Source-native projects retain the
exact result and admitted data views in report members with source hashes.

This first benchmark is synthetic, two-phase, linear, averaged-drive and
quasi-steady BEM. It is not a VESC firmware/switching model, product motor,
blade-resolved CFD, thermal coupling or full flight. Its explicit optional
Studio-source/compiler dependency fails closed in a frozen worker without that
runtime. These gates must survive packaging; no new UI language or external
solver implementation is introduced. Larger/nonlinear moving-mesh and rotating
fluid work require separately derived and verified extensions.

The three independent method records under `docs/validation/PROPULSION_POD_*`
and focused analytical/adversarial/refinement tests govern numerical changes.
