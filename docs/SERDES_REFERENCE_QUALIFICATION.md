<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# 10.3125 GBd SERDES reference qualification

`scripts/qualify_serdes_reference.py` is a bounded regression of SPIKE's public
source-to-receiver SI workflow at exactly 10.3125 GBd. It qualifies only a
linear NRZ numerical foundation suitable for KR/SFI-like channel exploration.
It is not an IEEE 802.3 compliance procedure and does not qualify hardware.

Run from the repository root:

```powershell
build\qualification-py311\Scripts\python.exe scripts\qualify_serdes_reference.py
build\qualification-py311\Scripts\python.exe -m unittest tests.python.test_serdes_reference -v
```

The runner prints deterministic, bounded JSON and exits nonzero if any criterion
fails. It checks:

- an exact 10.3125 GBd inverse-transform grid at 16 samples/UI;
- complex loaded transfer against an original analytic matched, delayed,
  attenuating two-port (`0.8 * exp(-j*2*pi*f*173 ps)`, with the expected 1/2
  Thevenin/load division);
- a shunt-capacitor transfer against `1/(2 + j*2*pi*f*50*C)`;
- an absolute time-domain oracle: zero edge time, one-UI (16-sample) delay and
  matched loading must produce a 0.4 V eye from the 0.8-gain channel;
- eye-height sensitivity between grids providing 8 and 16 samples/UI, with an
  acceptance bound of 10 mV; and
- fixed-band frequency-grid refinement sensitivity for a matched lossless line with a
  1.2 pF receiver shunt: at fixed 82.419512195 GHz bandwidth, requested bit
  rate, source, load and RC model, refine 257/513/1025/2049/4097/8193
  frequency points; the exact source-clock and fractional receiver sampler keep
  every represented rate at 10.3125 GBd, and the final successive eye-height
  change must not exceed 0.2 mV; and
- explicit blocking of a grid with fewer than 8 samples/UI.

The analytic networks are synthetic numerical oracles. They are not simulated
measurements, measured fixtures, connector/cable models, or validation against
laboratory data. The runner does not evaluate masks, insertion/return-loss
limits, COM, BER, jitter, CDR, equalization, link training, or interoperability.
The workflow continues to report `production_qualified: false` and
`compliance_status: not_evaluated`.

The 8/16 samples-per-UI comparison is deliberately reported as bandwidth and
sampling sensitivity, not convergence: changing that grid also changes sampled
bandwidth and transform period. The separate four-level experiment holds the
physical bandwidth, source, load, RC model and bit rate fixed. The exact source
clock and fractional receiver sampler preserve 10.3125 GBd even though changing
`N` changes frequency spacing and transform period. The JSON records the
represented rate and error at every level. The successive changes need not be
monotonic, so this is refinement evidence rather than a strict monotonic
convergence proof or an estimate of solution error. The 0.2 mV final-delta
threshold is a local, non-normative engineering repeatability gate; it does not
come from IEEE limits or establish accuracy. The analytic complex-gain, analytic RC
frequency response, and 0.4 V matched-eye checks are the absolute numerical
oracles. Output records each workflow request SHA-256 plus Python and NumPy
runtime versions so a result can be tied to its exact inputs and runtime.

This scope also excludes 10GBASE-T. BASE-T requires a twisted-pair PHY with
PAM16 signaling, DSP, echo/crosstalk cancellation and protocol-specific link
behavior that this linear NRZ workflow does not implement.

## Method provenance

The 10.3125 GBd reference rate is motivated by the IEEE 802.3 public presentation
[10GBASE-KR PMD](https://ieee802.org/3/ap/public/jan05/brink_01_0105.pdf).
That presentation is not used as a source of normative qualification limits.
The current [IEEE 802.3 COM public area](https://www.ieee802.org/3/ad_hoc/COM/public/index.html)
is listed for context only; no COM code, data, limits, or prose were copied or
adapted. Equations, fixture generation, criteria and code in this regression
were independently authored for SPIKE. New source files retain the repository's
existing mixed-license boundary pending the ownership review required by
`LICENSING.md`.
