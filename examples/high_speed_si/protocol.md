<!-- SPDX-License-Identifier: Apache-2.0 -->
# Protocol-rate SI studies

These are actual executions of SPIKE's existing integrated source-to-receiver
backend through `python.spike_core.service.handle`, method `run_si_workflow`.
They use original synthetic inputs and preserve the backend's experimental,
not-production-qualified and not-evaluated-compliance status. The runs do not
establish PCB accuracy or Ethernet/LVDS compliance.

## Architecture and stimulus

| Case | Aggregate payload | Architecture | Simulated lane rate | UI |
| --- | --- | --- | --- | --- |
| ethernet_1g | 1 Gbit/s | 1000BASE-X host serial reference, 8b/10b | 1.25 GBd NRZ | 800 ps |
| ethernet_10g | 10 Gbit/s | 10GBASE-R/KR reference, 64b/66b | 10.3125 GBd NRZ | 96.970 ps |
| ethernet_100g | 100 Gbit/s | 100GBASE-KR4, four physical lanes | 25.78125 GBd NRZ, one representative lane | 38.788 ps |
| lvds_1g | User-defined | LVDS differential-mode illustration | 1 GBd NRZ | 1000 ps |
| serdes_32g | User-defined | Generic serial link | 32 GBd NRZ | 31.25 ps |

100GBASE-KR4 includes PCS coding, 256b/257b transcoding and RS-FEC; the selected
lane rate includes the architecture overhead. This study executes only one
representative lane and does not encode, bond, skew-align, train or decode
four lanes. Every waveform uses SPIKE's deterministic 256-bit PRBS7. No PCS,
FEC or Ethernet frames are simulated.

The 1G case represents the host serial interface; it is not 1000BASE-T or a
fiber propagation model. The 10G case is not 10GBASE-T. A single 100 GBd lane
and PAM4 variants of 100G are not interchangeable with this selected KR4
architecture. LVDS itself does not prescribe the chosen 1 GBd rate or a PCS
encoding. Generic SerDes does not imply a named protocol.

## Model and units

Each case uses an 80 mm uniform differential equivalent line with
R = 8 ohm/m, L = 500 nH/m, C = 50 pF/m and loss tangent = 0.006.
The ideal lossless modal impedance is sqrt(L/C) = 100 ohm and propagation speed
is 1/sqrt(LC) = 2e8 m/s, giving 400 ps delay.

Each two-port represents differential voltage and differential loop current,
with a 100 ohm reference, source resistance and receiver resistance. This is
an explicit scalar modal equivalent, not a four-port extraction: it has no
common mode, imbalance, pair skew or mode conversion. No PCB/cable geometry
determines these RLGC values.

The receiver has 0.15 pF capacitance. Source rise/fall time is 0.15 UI.
Ethernet/SerDes sources use open-circuit levels -0.8/+0.8 V, producing ideal
matched receive levels -0.4/+0.4 V. Those levels are illustrative, not protocol
requirements. LVDS uses open-circuit -0.7/+0.7 V to represent nominal
matched differential receive levels -0.35/+0.35 V. The source is a Thevenin
equivalent, not a transistor/current-steering LVDS model. VIL/VIH are -0.1/+0.1 V;
only the LVDS choice is motivated by the cited typical receiver threshold.
Common-mode offset and allowed common-mode range are not modeled.

The base grid has 513 frequencies including DC, with stop frequency
rate * 16 * 512/1025, providing exactly 16 samples/UI. The highest synthetic
bandwidth is 255.750244 GHz in the 32 GBd case. Constant R/L/C/loss tangent at
that bandwidth is an illustrative numerical model, not a material or conductor
accuracy claim. Skin/proximity effects, frequency-dependent dielectric
dispersion, packages and connectors need supplied validated models.

## Executed results (2026-10-10)

| Case | Base 513-point eye (V) | Finest tested eye (V) | Final refinement delta (mV) | Channel insertion loss near Nyquist (dB) |
| --- | ---: | ---: | ---: | ---: |
| ethernet_1g | 0.794012 | 0.797998 | 2.981480 | 0.068682 |
| ethernet_10g | 0.764098 | 0.765438 | 0.091969 | 0.365142 |
| ethernet_100g | 0.587120 | 0.589838 | 0.564414 | 0.871152 |
| lvds_1g | 0.688156 | 0.701525 | 0.385815 | 0.060507 |
| serdes_32g | 0.504892 | 0.509954 | 1.341822 | 1.074594 |

The saved native results and plots contain the base grid results. The summary
separately records refinement values. Insertion loss is unloaded matched
channel S21 at the nearest frequency sample, whose actual frequency is saved;
the loaded eye includes the source resistance and receiver capacitance.

All five cases pass the final local numerical checks. LVDS initially failed
the unchanged 5 mV refinement gate: the 1025-to-2049 point delta was
7.355319 mV. Following that failure, 4097 and 8193 points gave successive
changes of 0.660251 and 0.385815 mV. The original failure is retained as
`initial_2049_point_refinement_pass: false`. The coarse LVDS eye differs from
the finest eye by 13.368402 mV; the coarse result must not be called converged.
The small finest-grid overshoot beyond 0.700 V is retained, not clipped.

These are fixed-band frequency-spacing/transform-period sensitivity checks,
not a mathematical convergence proof or solution-error estimate. Point counts
are 513/1025/2049 for the other cases; all physical parameters and requested
symbol rates stay fixed. The final 5 mV threshold is a declared local,
non-normative engineering gate, not a standard limit.

## Numerical oracles

The independent scalar ABCD oracle uses z = R + j*w*L,
y = (loss_tangent + j)*w*C, gamma = sqrt(z*y),
A = D = cosh(gamma*length), B = z*sinh(gamma*length)/gamma,
C_abcd = y*sinh(gamma*length)/gamma. The DC quotient is evaluated with its
limit, length. With source resistance Rs and receiver admittance YL,

`Vreceiver/Vsource = 1 / (A + B*YL + Rs*(C_abcd + D*YL))`.

This compares against the backend's matrix-exponential and wave-boundary
implementation, including the receiver capacitance. Maximum absolute complex
transfer error at the base grids is below 6.6e-15; the acceptance limit is
1e-10. This verifies numerical agreement for the stated model, not the model's
correspondence to a board.

An additional independently constructed matched, lossless one-UI line with
zero source edge time and zero receiver capacitance must return an eye equal
to half the open-circuit peak-to-peak swing: 0.8 V, or 0.7 V for LVDS.
All five pass the 1e-10 V absolute tolerance. Each rate is represented within
0.01 Hz. Passive-channel checks pass. Reducing bandwidth eightfold correctly
blocks time-domain output with the backend's minimum-eight-samples/UI message.
Every result withholds spatial fields and production/compliance qualification.

## Reproduce and inspect in SPIKE

From the repository root:

```powershell
build\qualification-py311\Scripts\python.exe examples\high_speed_si\run_protocol_cases.py
build\qualification-py311\Scripts\python.exe -m unittest tests.python.test_si_workflow tests.python.test_serdes_reference tests.python.test_si_protocol_suites tests.python.test_si_protocol_test_runner -q
```

The runner exits nonzero if any declared check fails. On this run it exited 0.
The four focused regression modules passed 53 tests. Runtime: Python 3.11.9,
NumPy 2.4.6, SciPy 1.17.1. No solver algorithm was changed. Summary JSON records
the Git HEAD, script/backend source hashes, request hashes and runtime versions.

- `protocol_inputs/<case>.json`: native `spike/si-workflow-request/v1`.
- `protocol_results/<case>.json`: complete native `spike/si-workflow-result/v1`,
  including request, waveforms, eyes, transfer, network, TDR and limitations.
- `protocol_results/<case>.s2p`: channel only; endpoint loading is excluded.
- `protocol_results/summary.json`: compact per-case metrics and check evidence.
- `*_matched_oracle.json` and `*_insufficient_bandwidth.json`: reproducible
  absolute oracle and rejection inputs. Refinement requests are reproduced by
  changing only `channel.frequency_points` as recorded in the summary.

Open HF / SI, S-parameter workbench, Source-to-receiver workflow, then load the
setup/result JSON. The UI accepts both native contracts; loading a result also
loads its embedded request and displays the saved plots. The result is about
this synthetic network regardless of any board shown beside it.
`SiWorkflowWorkbench.tsx` lines 109-112 implement this import. A project
package stores a result at `analysis.si.latest_channel_result`;
`App.tsx` lines 2163-2164 restore either the channel-result or workflow-result
contract. This script does not create a project package or claim a desktop
visual verification.

Spatial E/H/current-density field probes, full-wave PCB propagation, actual
lane crosstalk, measured correlation, manufacturing tolerance, nonlinear IBIS,
AMI, COM, masks, BER, equalization and protocol interoperability are not
established by these runs. A separate full-wave run must retain its own
geometry, ports, material/boundary inputs, mesh convergence and applicability.

## Primary references and provenance

Sources reviewed 2026-10-10:

- [Intel 1000BASE-X/SGMII PCS documentation](https://www.intel.com/content/www/us/en/docs/programmable/813669/24-1-4-0-0/1000base-x-sgmii-pcs-with-optional-embedded.html)
  identifies the 1.25 Gbit/s serial interconnect and Clause 36 PCS.
- [AMD PG047](https://docs.amd.com/api/khub/documents/3XPo6rkH7c~9F7vB3mrvOw/content)
  documents 1.25 Gbit/s output and 8b/10b encoding for 1000BASE-X.
- [Altera 10GBASE-R/KR documentation](https://docs.altera.com/r/docs/683779/current/stratix-v-device-handbook-volume-2-transceivers/gbase-r-and-10gbase-kr)
  states 10 Gbit/s at XGMII and 10.3125 Gbit/s serial with 64b/66b.
- [IEEE-hosted Ethernet coding overview](https://www.ieee802.org/3/400GSG/email/pdf7vtAkT89g3.pdf)
  describes four 25.78125 Gbit/s KR4/CR4 lanes with transcoding and RS coding.
  This public overview is architecture context, not a normative compliance limit.
- [TI LVDS Overview](https://www.ti.com/de-de/video/5773281943001)
  explains nominal 350 mV differential levels, 100 ohm loading and 100 mV
  receiver thresholds.

Only architecture/rate facts informed this original study. No external code,
test data, board files, vendor models or prose were copied or adapted.
All model parameters, code, derived oracles and explanatory text here are
original. SPIKE-owned Apache-2.0 licensing applies.

