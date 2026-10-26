<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Original SI reference requests

`pam3-generic-worker.json` is an original three-level, 20 GBd sampled-channel
reference, not USB4 traffic or a board-derived channel. Run the actual worker:

```powershell
Get-Content examples/si/pam3-generic-worker.json -Raw | .venv/Scripts/python.exe -m python.spike_core.service
```

Expected output contains two eyes near 0.4 V before the declared 10 mV RMS
decision noise, explicit thresholds, measured and conditional Gaussian SER,
`modulation: PAM3` and `production_qualified: false`. Read the actual noisy
eye openings rather than treating the noiseless value as an asserted result.
See [PAM3 math, assumptions and API](../../docs/SI_PAM3.md). Its dimensionless
FIR taps are not continuous-time AMI Init impulse samples. Executable AMI is
the separate [trusted-development native host](../../docs/SI_AMI_EXECUTION.md).

`10g-nrz-cdr.json` is an independently authored MIT/SigHarmonic example, not
copied hardware or measured data. It exercises a matched 1cm ideal line with
finite transmitter edges, a loaded receiver and optional timing recovery at
10.3125 GBd. The broad frequency band supports time resolution; it is not a
claim that a real cable/board has these lossless parameters to 160GHz.

The received voltage is approximately 0--0.5V, hence a 0.25V CDR threshold.
The initial phase is a declared approximate starting boundary, not measured
training evidence. No Ethernet mask, bit-error probability or hardware lock
is certified. Use `scripts/qualify_cdr_workflow.py` for execution and checks.
