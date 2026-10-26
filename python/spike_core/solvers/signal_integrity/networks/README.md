<!-- SPDX-License-Identifier: Apache-2.0 -->
# Signal Integrity / Networks

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/signal-integrity/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [multiport_calibration.py](multiport_calibration.py)
- [one_port_calibration.py](one_port_calibration.py)
- [si_candidate_study.py](si_candidate_study.py)
- [si_multiboard.py](si_multiboard.py)
- [si_network_graph.py](si_network_graph.py)
- [si_network_workflow.py](si_network_workflow.py)
- [sparameter_capacitive_terminated.py](sparameter_capacitive_terminated.py)
- [sparameter_crosstalk_timing.py](sparameter_crosstalk_timing.py)
- [sparameter_deembedding.py](sparameter_deembedding.py)
- [sparameter_inductive_terminated.py](sparameter_inductive_terminated.py)
- [sparameter_modes.py](sparameter_modes.py)
- [sparameter_multi_aggressor.py](sparameter_multi_aggressor.py)
- [sparameter_multiport_deembedding.py](sparameter_multiport_deembedding.py)
- [sparameter_rational.py](sparameter_rational.py)
- [sparameter_reflectometry.py](sparameter_reflectometry.py)
- [sparameter_rlc_energy.py](sparameter_rlc_energy.py)
- [sparameter_rlc_initial.py](sparameter_rlc_initial.py)
- [sparameter_rlc_terminated.py](sparameter_rlc_terminated.py)
- [sparameter_sampling.py](sparameter_sampling.py)
- [sparameter_terminated.py](sparameter_terminated.py)
- [sparameter_transient.py](sparameter_transient.py)
- [sparameters.py](sparameters.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
