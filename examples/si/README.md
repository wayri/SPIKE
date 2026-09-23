<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Original SI reference requests

`10g-nrz-cdr.json` is an independently authored MIT/SigHarmonic example, not
copied hardware or measured data. It exercises a matched 1cm ideal line with
finite transmitter edges, a loaded receiver and optional timing recovery at
10.3125 GBd. The broad frequency band supports time resolution; it is not a
claim that a real cable/board has these lossless parameters to 160GHz.

The received voltage is approximately 0--0.5V, hence a 0.25V CDR threshold.
The initial phase is a declared approximate starting boundary, not measured
training evidence. No Ethernet mask, bit-error probability or hardware lock
is certified. Use `scripts/qualify_cdr_workflow.py` for execution and checks.
