<!-- SPDX-License-Identifier: Apache-2.0 -->
# Signal integrity and sampled networks

[All solver families](../README.md) · [SI setup](../../SI_WORKFLOW.md) ·
[User guide](../../SI_USER_GUIDE.md)


Completion labels describe bounded implementation, not physical or release
qualification. See [all capability completion states and remaining work](../completion.md).

## Geometry-derived channels and loss

| Subgroup | Code owner | Method and boundary | Completion state |
| --- | --- | --- | --- |
| Single line | [si_channel.py](../../../python/spike_core/solvers/signal_integrity/channels/si_channel.py) | Admitted planar quasi-TEM approximation and telegrapher network | Partial / experimental within stated scope |
| Coupled pair | [si_coupled_channel.py](../../../python/spike_core/solvers/signal_integrity/channels/si_coupled_channel.py) | Sparse electrostatic cross-section C and homogeneous quasi-TEM L | Partial / experimental within stated scope |
| Supplied geometry/material scenarios | [Pair geometry](../../../python/spike_core/solvers/signal_integrity/channels/si_pair_geometry.py), [material scenarios](../../../python/spike_core/solvers/signal_integrity/channels/si_material_scenario.py) | Explicit source/reference geometry and revision-bound material assumptions | Partial / experimental within stated scope |

See [geometry admission](../../GEOMETRY_DERIVED_SI_CHANNEL.md),
[high-frequency loss laws](../../HIGH_FREQUENCY_LOSSES.md) and
[real-board evidence](../../validation/SI_BOARD_SCENARIOS_20261023.md).
Skin/roughness laws do not resolve arbitrary proximity currents. Reference planes,
returns and discontinuities must remain explicit. Diagnostic extracted paths are
not general board compliance; the dated worker record retains actual pair rejections.

## Distributed lines, connection graphs and loss

[Network graph](../../../python/spike_core/solvers/signal_integrity/networks/si_network_graph.py) eliminates
declared internal wave ports with conditioned linear solves, including multiple
reflections. It does not create missing connector physics.

| Subgroup | Method/evidence guide | Completion state |
| --- | --- | --- |
| Uniform RLGC and driven fields | [Line network](../../RLGC_LINE_NETWORK.md), [fields and integrated loss](../../RLGC_LINE_FIELDS.md) | Partial / experimental within stated scope |
| Cascades, ideal junctions and finite supplied corners | [Cascade](../../RLGC_LINE_CASCADE.md), [junction](../../RLGC_LINE_JUNCTION.md), [candidate study](../../SI_CANDIDATE_STUDY.md) | Partial / experimental within stated scope |
| Coupled physical lines and loads | [Coupled pair](../../RLGC_COUPLED_PAIR.md), [terminations](../../RLGC_TERMINATED_PAIR.md) | Partial / experimental within stated scope |
| Lossless and distortionless time-domain propagation | [Lossless delay recursion](../../LOSSLESS_LINE_TRANSIENT.md), [attenuating reference](../../DISTORTIONLESS_LINE_TRANSIENT.md) | Partial / experimental within stated scope |

The `rlgc_*` modules in `python/spike_core/` own individual supplied-line
compositions. Analytic propagation avoids a volume mesh but relies on declared
uniform-line laws. Finite corner/sample extrema are not continuous-band bounds.

## Sampled network processing and time response

| Subgroup | Source owner | Boundary | Completion state |
| --- | --- | --- | --- |
| Wave normalization/conversion | [sparameters.py](../../../python/spike_core/solvers/signal_integrity/networks/sparameters.py) | Explicit port ordering, polarity and real-reference conventions | Implemented within stated scope |
| Sampling and DC | [Sampling](../../../python/spike_core/solvers/signal_integrity/networks/sparameter_sampling.py) | Admitted sampled grids and explicit data policy | Implemented within stated scope |
| Rational fit | [Rational owner](../../../python/spike_core/solvers/signal_integrity/networks/sparameter_rational.py) | Supplied stable poles and checked fit, not general passive causal completion | Partial; supplied-pole fit only |
| Prescribed/loaded transients | [Transient](../../../python/spike_core/solvers/signal_integrity/networks/sparameter_transient.py), [termination](../../../python/spike_core/solvers/signal_integrity/networks/sparameter_terminated.py), [RLC](../../../python/spike_core/solvers/signal_integrity/networks/sparameter_rlc_terminated.py) | Admitted state-space model, initial states and physical boundary equations | Partial / experimental within stated scope |
| Reflectometry | [Reflectometry](../../../python/spike_core/solvers/signal_integrity/networks/sparameter_reflectometry.py) | Explicit wave/current reconstruction; unresolved apparent ratios remain unresolved | Partial / experimental within stated scope |
| Coupled fixture removal | [Multiport de-embedding](../../../python/spike_core/solvers/signal_integrity/networks/sparameter_multiport_deembedding.py) | Simultaneous wave solve for supplied coupled fixture/DUT partitions | Partial / experimental within stated scope |

Other `sparameter_*` owners cover initialized energy, reactive terminations,
multi-aggressor and timing-corner processing. Start at
[mathematics](../../SOLVER_MATHEMATICS.md) for those linked derivations.
The [multiport workflow](../../MULTIPORT_DEEMBEDDING.md) has a dedicated SI panel;
[SI08 closure](../../SI08_FAMILY_CLOSURE.md) separates bounded integration from
open calibration, uncertainty, correlation and release gates.

## Eyes, receiver diagnostics and model execution

| Subgroup | Owner and evidence | Scope | Completion state |
| --- | --- | --- | --- |
| NRZ/PAM4 workflows | [Workflow](../../../python/spike_core/solvers/signal_integrity/receivers/si_workflow.py), [PAM4](../../../python/spike_core/solvers/signal_integrity/receivers/si_pam4_eye.py), [eye masks](../../SI_EYE_MASK_TESTING.md) | LTI waveforms, finite receiver statistics and bounded equalization; no automatic compliance | Partial / experimental within stated scope |
| Generic PAM3 | [PAM3](../../../python/spike_core/solvers/signal_integrity/receivers/si_pam3.py), [execution record](../../validation/SI_EXECUTION_20261023.md) | Sampled-FIR study; unsupported protocol use is rejected | Partial / experimental within stated scope |
| Resonance and Q | [Resonance](../../../python/spike_core/solvers/signal_integrity/receivers/si_resonance.py), [ringdown](../../../python/spike_core/solvers/signal_integrity/receivers/si_ringdown.py) | Supplied RLC/half-power/free-decay estimates, not general eigenmode qualification | Partial / experimental within stated scope |
| AMI | [Inventory](../../../python/spike_core/solvers/signal_integrity/receivers/si_ami_inventory.py), [supervisor](../../../python/spike_core/solvers/signal_integrity/receivers/si_ami_execution.py), [native host](../../../src/solvers/signal_integrity/si/ami_host_main.cpp) | Separate trusted development execution; vendor package/rights/admission remains explicit | Partial; trusted development execution only |
| Native CDR reference | [transition_pi_cdr.cpp](../../../src/solvers/signal_integrity/si/transition_pi_cdr.cpp) | Internal reference, not universal dynamic receiver/compliance support | Implemented reference only |

## Setup and verification

Use the SI panel, dedicated multiport panel or exact guarded runner in
[the integration map](../../SOLVER_INTEGRATION.md). Supply source bandwidth,
reference impedance/plane, all ports, terminations, driver and receiver assumptions.
Keep field extraction separate from processing supplied Touchstone data.

Entry checks include `tests/python/test_si_channel.py`, `test_si_network_graph.py`,
`test_sparameter_multiport_deembedding.py`, `test_si_pam3.py` and the `test_rlgc_*`
and `test_sparameter_*` families. Compare independent boundary equations,
normalization, conservation, fit quality and refinement. Gaussian BER proxies,
finite-band passivity screens and smooth plots are not measured compliance.
