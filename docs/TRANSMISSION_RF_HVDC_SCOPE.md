<!-- SPDX-License-Identifier: Apache-2.0 -->
# Transmission lines, high-speed radio and HVDC infrastructure

Requested scope recorded 14 October 2026. These are requirements and proposed
acceptance gates, not newly implemented or qualified solver capabilities.
The [parity-first execution policy](HYPERLYNX_PARITY_AND_MULTIPHYSICS_PLAN.md#active-parity-and-deferred-expansion)
remains active. High-speed interconnects and local RF extraction extend the
existing SI/EM parity work. Radio-system and utility-infrastructure additions
remain deferred until original parity establishment.

## Simulation levels and boundaries

| Level | Required capability | Active/deferred work |
| --- | --- | --- |
| PCB/package/coax/cable transmission lines | Single-ended, differential and multiconductor lines; explicit returns, frequency-dependent RLGC, delay/reflections, terminations, discontinuities, crosstalk and waveform/eye/TDR/S-parameter observables | Active SI01/SI02/SI03/SI07/SI08 and EM01-EM03 parity foundations; current scope remains bounded |
| RF hardware and high-speed radio | RF ports/matching, filters, LNAs/PAs/mixers/oscillators, antenna feeds, nonlinear/noise effects, modulation and receiver metrics | Local board/antenna extraction stays in parity; RF01/RF02 system simulation is post-parity |
| Utility lines and HVDC links | Overhead/submarine/underground cable geometry, earth/metallic return, traveling waves, converter stations, controls, AC/DC networks and faults | PW01-PW05 are post-parity infrastructure requirements |

For every study declare carrier frequency, occupied bandwidth, data/symbol rate,
signal/power levels, line lengths/geometry, frequency range, voltage/power bases,
operating point, waveform/mesh/time resolution and requested error. The phrase
high speed does not specify a frequency band or data rate. A length unit or
voltage change does not extend a model's physical validity.

Current evidence: [SI workflow](SI_WORKFLOW.md), [network processing](SIGNAL_INTEGRITY_NETWORK_WORKBENCH.md),
[harness engineering](HARNESS_ENGINEERING.md) and [solver status](SOLVER_STATUS.md).
Supplied RLGC/Touchstone and bounded harness/circuit studies do not establish
general shielded cable extraction, a complete radio chain or a qualified HVDC
network. Existing converter/PWM evidence is not utility-converter qualification.

## Transmission-line parity requirements

Retain per-unit-length matrix units and conductor/return/port identity. Support
supplied or independently extracted RLGC across declared frequency/material
ranges; geometry families must be explicit. Include coupled lines, branches,
connectors/vias/launches, shield/ground behavior where admitted and passive causal
broadband fitting for time-domain circuit coupling. Do not silently replace
distributed delay with a lumped element or invent DC data from a frequency sweep.

Original acceptance cases should cover lossless matched-line delay and impedance,
open/short reflections, mismatch multiple reflections, attenuation/dispersion,
coupled modes and port permutation. Require passivity/causality policies,
sampling/band/time-window refinement, circuit power balance and independent
VNA/TDR or measured waveform comparison. Geometry extraction has separate mesh,
material and boundary convergence gates from supplied-network execution.

## RF and radio requirements

Keep device/circuit, envelope/baseband and electromagnetic field models distinct.
Specify admissible carrier/envelope bandwidth, nonlinear model range, bias,
temperature, noise convention and sampling. Link passive measured/extracted
multiports to nonlinear RF devices without discarding impedance or noise effects.
Targets include harmonic/intermodulation response, compression, spectral regrowth,
phase noise, IQ imbalance, modulation/demodulation, EVM, BER with statistical
confidence, sensitivity and channel/link performance. Add antenna arrays/MIMO,
polarization, matching/radiation efficiency and declared propagation models.

[MathWorks circuit-envelope documentation](https://www.mathworks.com/help/simrf/gs/circuit-envelope-basics.html)
describes a carrier/envelope modeling distinction and associated bandwidth and
nonlinearity limits. This informs scope selection, not a SPIKE implementation.
Use full passband or field methods when an envelope approximation is inadmissible.
A solved antenna pattern does not by itself verify a radio's data throughput.

Proposed gates: original linear chain/noise references with declared matching
assumptions; nonlinear two-tone and modulated fixtures; carrier/sample/band
refinement; independent spectra/EVM/BER measurements or references; calibrated
antenna/propagation and link power accounting. Report model availability, physics
execution and predictive qualification separately.

## HVDC and utility infrastructure requirements

Use a graph of buses, stations, converter/transformer/filter/protection models,
distributed lines/cables and explicit grounding/return networks. Declare pole,
phase, conductor and reference identities, SI/per-unit bases and initial state.
Large-network studies need DC/AC load flow and control/stability models as well
as electromagnetic transients; these are different resolution levels.

- **PW01:** frequency-dependent line/cable models with DC behavior, skin/proximity,
  dielectric loss, earth return, mutual coupling and propagation delay; distinguish
  constant-parameter, modal and phase-domain applicability.
- **PW02:** LCC/VSC/MMC converter models, switching or averaged/equivalent resolution,
  converter transformers, filters/reactors, submodule energy/balancing, PLL and
  voltage/current/power/droop controls where applicable. Averaged validation does
  not establish switching harmonics or semiconductor stress.
- **PW03:** DC/AC faults, breaker/arrester/protection models, surge/traveling waves,
  energization/restart and converter/control interactions. Fault timing, interruption
  energy and peak stress require dedicated timestep/model/reference evidence.
- **PW04:** multi-terminal networks, load flow, contingencies, control interactions,
  small-signal/large-signal stability and conservative EMT/phasor/reduced co-simulation;
  checkpoint/restart and scale/resource benchmarks.
- **PW05:** conductor/cable ampacity and heating, insulation electric fields,
  ground/electrode potentials and local station EM/thermal/mechanical effects using
  qualified local models. Applicable limits and standards require declared editions;
  a numerical field or waveform is not automatic infrastructure signoff.

The official [PSCAD line-model description](https://www.pscad.com/webhelp/EMTDC/Transmission_Lines/Frequency_Dependent_Models.htm)
distinguishes frequency-dependent modal and phase-domain traveling-wave models.
[EMTP's application scope](https://emtp.com/applications/all-applications) includes
power-system transients and MMC-HVDC models. These are comparator/method references;
no vendor implementation, model library or example network is copied or licensed
by this plan.

Proposed acceptance starts with an original lossless/lossy line and DC operating
point, then a declared two-terminal averaged converter/link, then frequency-dependent
coupled cables and multi-terminal/fault cases. Add switching/MMC, protection and
network-scale coupling only after their separate gates pass. Require independent
reference/measurement availability and rights, DC/transient frequency applicability,
initialization consistency, mesh/fit/timestep refinement and power/energy balance.

## Scale, execution and delivery order

Reuse neutral network, circuit, geometry/material and study identities. Broad
grid EMT/control work should extend the circuit/network boundary rather than
force every kilometer of infrastructure into a global PCB/full-wave mesh.
Use local field extraction, causal reduced multiports and appropriate distributed
network models; conserve energy/phase/port conventions at interfaces.

Profile actual admitted workloads before selecting sparse/matrix-free, FFT,
CPU/GPU or distributed execution. Partitioning independent sweeps is not
single-solve decomposition. Multi-rate/hybrid coupling needs synchronization,
rollback and conservation evidence. Do not claim real-time/HIL capability from
offline execution time alone.

The active sequence remains original parity, with transmission-line and local
RF requirements incorporated into SI/EM tasks. After parity, refine RF01/RF02
and PW01-PW05 into source-bound stage fixtures and solver-suite implementations,
alongside the separately deferred general physics/optics program. Only actual
accepted benchmarks can move these capabilities from Planned to Done.
