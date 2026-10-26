<!-- SPDX-License-Identifier: Apache-2.0 -->
# Signal Integrity / Receivers

[Methods, setup routes, validity and evidence](../../../../../docs/solvers/signal-integrity/README.md)

Implementation files are organized here by responsibility. Moving them did not
change governing equations, tolerances or request/result contracts. Runtime
services and stable command entry points remain in `python/spike_core/`.

## Source owners

- [si_ami_execution.py](si_ami_execution.py)
- [si_ami_inventory.py](si_ami_inventory.py)
- [si_clock_recovery.py](si_clock_recovery.py)
- [si_crosstalk.py](si_crosstalk.py)
- [si_ethernet_qualification.py](si_ethernet_qualification.py)
- [si_eye_mask.py](si_eye_mask.py)
- [si_eye_mask_profiles.py](si_eye_mask_profiles.py)
- [si_ibis.py](si_ibis.py)
- [si_pam3.py](si_pam3.py)
- [si_pam4_eye.py](si_pam4_eye.py)
- [si_passives.py](si_passives.py)
- [si_protocol_eye_mask.py](si_protocol_eye_mask.py)
- [si_protocol_suites.py](si_protocol_suites.py)
- [si_protocol_test_runner.py](si_protocol_test_runner.py)
- [si_resonance.py](si_resonance.py)
- [si_ringdown.py](si_ringdown.py)
- [si_statistical_eye.py](si_statistical_eye.py)
- [si_symbol_clock.py](si_symbol_clock.py)
- [si_workflow.py](si_workflow.py)
- [si_workflow_resonance.py](si_workflow_resonance.py)

See the linked domain guide before treating source availability as numerical
or release qualification. Historical source-bound receipts retain their original
hashes and require fresh validation for this layout.
