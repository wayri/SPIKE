<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# SERDES / actuator delivery and research review

Updated 2026-09-20. All requested interfaces and actuator classes are in scope;
none may inherit qualification from another. This is the remaining implementation
plan, not a declaration that these capabilities now exist.

| Workflow | Executable increment | Required before qualification |
|---|---|---|
| 10GBASE-KR | [10.3125 GBd linear numerical checks](SERDES_REFERENCE_QUALIFICATION.md) | Differential channel/package fixtures; specified transmitter, equalizer, dynamic CDR, jitter/noise; training and applicable normative tests; independent and measured correlation |
| SFI/XFI | Same NRZ numerical core, separately scoped | Correct interface revision, reference planes and electrical limits; module/ASIC models; receiver and interoperability evidence |
| 10GBASE-T | Existing generic multiport channel infrastructure only | Four-pair bidirectional PHY, PAM16/DSQ mapping, echo/NEXT/FEXT cancellation, timing recovery, coding/LDPC, training and qualified cable fixtures; NOT an NRZ preset |
| Reluctance | [Supplied-map virtual-work review](ACTUATOR_FORCE_MAP.md) | Public field process adapter; geometry/material/current compilation; nonlinear force and motion; mesh/stroke convergence and measurements |
| Permanent magnet / voice coil | Supplied-map review, including force/mass and ripple | PM force, polarity/orientation, cogging at zero current, demagnetization/model validity and measured force/stroke |
| Electrostatic | Supplied-map review at fixed voltage | Electrostatic force field workflow, electrodes/dielectrics, mechanics/pull-in, gap convergence and measured force/displacement |

Execution sequence: numerical reference corpus → public process contracts and
bounded field/device implementations → independent comparison → uncertainty-bound
measurement → packaged/platform qualification. Preserve explicit unsupported
states until the corresponding implementation and evidence exist.

Follow-up implementation: [fixed-excitation 1DOF motion](ACTUATOR_MOTION.md)
now connects any admitted class's supplied force map to displacement/velocity,
spring and damping. This closes bounded mechanical integration, not the field
generation, drive coupling or measured qualification rows above. Loaded NRZ
source timing now preserves the requested rate across grids, with independently
checked finite-ramp and RC time-domain regressions; see [workflow](SI_WORKFLOW.md).

## Recent primary research reviewed

Executable follow-up: [transition-PI CDR](SI_CLOCK_RECOVERY.md) is integrated
as an optional loaded receiver report, and [linear voice-coil drive](VOICE_COIL_DRIVE.md)
adds coupled current/back-EMF/motion. Neither closes interface qualification,
nonlinear geometry-derived actuator modeling, or measured correlation above.

These are new review records, not retrospective claims of implementation.
Publication dates are taken from publisher records, not search crawl dates.
The latest papers found in this focused search are listed; this is not an
exhaustive systematic review or a citation-count ranking.

- M. Jawad, H. Yu, F. Farrokh and Z. Ahmad, *Multi-Objective Optimization of a
  Rectangular Structured Linear Actuator Based on Taguchi Method*, ACES Journal
  41(1), January 2026: [publisher abstract and paper index](https://aces-society.org/search.php?no=1&type=2&vol=41).
  Abstract reviewed. Its force, force-to-PM-mass and cogging objectives motivate
  reporting separate metrics. Our moving-mass metric is explicitly different
  from PM mass. Taguchi optimization and its actuator geometry/results are not
  implemented or reproduced; field accuracy must precede optimization.
- *A dual-channel half-rate 32 Gb/s, 5.3 pJ/bit SerDes transceiver with 3-tap-FFE
  and CTLE in 28-nm CMOS for very short reach C2C and C2M interconnection* (2025),
  [DOI:10.1016/j.mejo.2025.106641](https://doi.org/10.1016/j.mejo.2025.106641).
  Publisher abstract indexed; direct full page unavailable during review.
  Candidate for transmitter/receiver architecture comparison, not proof that a
  generic software equalizer models a specific receiver or qualifies Ethernet.
- *A high speed adaptive reflection cancellation equalization circuit with
  Floating Tap FFE and Loop-Refactored DFE for ADC-DSP-based wireline receiver*
  (2025), [DOI:10.1016/j.mejo.2025.106612](https://doi.org/10.1016/j.mejo.2025.106612).
  Publisher abstract indexed; full text not reviewed. Candidate only: future
  sparse delayed-tap evaluation must compare against conventional FFE/DFE on
  identical channels, training budgets and held-out data. No claimed paper BER
  or FPGA performance is adopted as a SPIKE result.
- *Vacuum-gap electrostatic multilayer actuators for space robotics* (2025),
  [Nature Communications publisher record](https://www.nature.com/articles/s41467-025-66232-7).
  Candidate measured electrostatic validation source. Admission needs exact
  geometry, materials, boundary conditions, data rights and uncertainties;
  it is not evidence for the ideal capacitor example.

## Standards and evidence boundary

The [IEEE COM public area](https://www.ieee802.org/3/ad_hoc/COM/public/index.html)
provides current activity context, not a universal 10GbE compliance recipe.
The [IEEE 802.3an archive](https://www.ieee802.org/3/an/) is the primary BASE-T
standards-development entry. Draft presentations are not final normative limits.
Use the correct published standard/interface revision for every acceptance rule;
record permitted source and applicable clause before advertising compliance.

All code/equations/examples in this increment are independently authored. No
external code, figures, proprietary device models or measurement data were
copied. Foundational physical laws remain necessary even when recent research
guides the roadmap. No learning-based replacement is admitted without out-of-
sample evidence, stability/resource bounds and accuracy against a reference.
