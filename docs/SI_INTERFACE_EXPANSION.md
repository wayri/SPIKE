<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI interface workflows and native execution plan

Owner scope, 23 October 2026: pre-layout and post-layout SI for generic serial
links/SerDes, LVDS, DDR/LPDDR, PCI/PCIe, PXI/PXIe, USB 3.x/USB4, parallel
display-pixel interfaces, DisplayPort and HDMI. Parallel DPI and DisplayPort
are separate requirements. Setup entries are not executable device models or
protocol qualification. These changes follow the independently authored method,
licensing and native/HPC policies; no external software implementation or
demonstration is source material.

## Current-generation policy

Owner clarification: target current **released** standards, not historical tool
examples. Retain older work only when its governing mathematics remains valid
or a specifically selected legacy interface still needs it. Never use an old
receiver, rate, encoding, mask or timing table as a substitute for the selected
current generation. Drafts are separate experimental targets, not released
compliance baselines. Every normative rule must bind its revision, errata,
source access and review date; do not automatically reinterpret saved studies
when a newer revision appears.

Public metadata checked 23 October 2026 anchors IBIS 8.0, USB4 v2's current
specification listing, DisplayPort 2.1b and HDMI 2.2. PCI-SIG's catalog now lists
PCIe **7.1**, dated 17 September 2026; the earlier 7.0 metadata is not the newest
revision. PCIe 8.0 draft 0.5 remains a separate draft target. JEDEC's exact current
DDR/LPDDR revisions still need authorized primary-catalog verification; do not
claim that an older family baseline establishes current-generation support.
Classic discrete-time stability mathematics may remain applicable without
making a classic physical receiver or legacy protocol model current.

## Existing execution and critical gaps

Existing `si_network_workflow.py` admits explicit RLGC, sampled networks and
bounded geometry sources; `si_workflow.py` connects source/load models and
aggressors. `si_channel.py` supports a narrow uniform geometry envelope.
The protocol runner executes bounded channel screening and retains experimental
status; it does not qualify general PCB/package extraction or standard compliance.
IBIS currently provides inventory and selected operating-point linearization,
not complete nonlinear switching. AMI inventory remains non-executing. A separate
[native trusted-development host](SI_AMI_EXECUTION.md) executes the bounded
Init/GetWave/Close lifecycle; no vendor or production qualification is implied.

New dedicated setup entries distinguish LPDDR, parallel DPI, USB 3.x and USB4 v2
PAM3. Existing identifiers remain compatible. LPDDR stays in the DDR family;
parallel DPI belongs to the MIPI family. A separate [generic PAM3 path](SI_PAM3.md)
executes sampled-FIR convolution, two eyes and two-threshold SER through
`simulate_si_pam3`. Generation-specific planning remains blocked where its
encoder/receiver and normative limits are absent; the protocol runner still
rejects PAM3 instead of silently running NRZ/PAM4. Generic legacy USB entries
and generic three-level FIR simulation are not USB4 v2 receiver models.

## Implementation order and acceptance

1. **Model identity and topology.** Retain exact model bytes/hashes, pin/lane and
   package mapping, corner/direction, reference nets, port order and plane,
   component placement and pre/post-layout source identity. AMI inventory must
   reject unsupported descriptors and remain non-executing. Require an explicit
   `.ibs` algorithmic-model association before future native-model execution.
2. **Isolated AMI host.** A dedicated native worker must implement the supported
   Init/GetWave/Close lifecycle, bounded buffers, sampling/clock-vector semantics,
   timeouts, crash isolation and approved dependency admission. Test original
   identity, FIR and stateful model fixtures independently; inventory success
   cannot authorize a DLL, establish ABI compatibility or certify a vendor model.
   Statistical and sample-by-sample paths must respect each declared model mode.
3. **Native measured hot paths.** First isolate the existing transition-PI CDR
   recurrence; preserve all gates and compare analytical, hand-computed and
   reference results before enabling a production binding. NumPy FFT and SciPy
   linear algebra already use compiled code; do not rewrite them merely to change
   languages. Later profile bounded FFE/DFE, convolution and eye-density workloads.
   Production numerical owners are portable C++20; Python remains control and
   reference code. No fast-math or relaxed tolerances to manufacture speed.
4. **Complete modulation and receivers.** Distinguish NRZ, PAM3 and PAM4;
   implement model-driven equalization/CDR, deterministic and statistical noise,
   encoded stimuli and applicable training. Known-symbol DFE is not a verified
   decision-directed receiver. Gaussian BER extrapolation is not proof of FEC
   or protocol acceptance. Keep raw waveforms distinct from plotting decimation.
5. **Clocked buses.** DDR/LPDDR, PCI/PXI and parallel display need actual
   source/strobe/receiver timing, load order, turnaround, coupled switching and
   package/PDN effects. Average lane group-delay differences are not simulated
   setup/hold margins. Revision-specific receiver and timing masks need reviewed,
   authorized standard input; do not infer limits from a family name.
6. **Post-layout qualification.** Bind board/assembly revision, return paths,
   vias, packages, connectors, loss/material models and extraction mesh. Compare
   extraction refinement and independent networks, then physical fixtures.
   Successful imported Touchstone processing does not qualify extraction.

Each step requires negative/adversarial cases, input/source/build identities,
unchanged numerical gates and reproducible evidence. Native benchmarks use
warm-up plus at least five measured runs, median and tail latency, allocation
and peak-memory accounting, compiler flags, CPU/thread and binary identities.
Compare end-to-end results, not kernel-only speed. Distribute independent lanes
and sweeps using existing trusted worker/LAN scheduling; partition one physical
field solve only through its native distributed backend. Coordinate outer jobs,
OpenMP and BLAS to avoid oversubscription.

## Primary source review boundary

Reviewed 23 October 2026; access is not redistribution permission.

| Primary source | What was actually reviewed / permitted inference |
| --- | --- |
| [IBIS 8.0](https://ibis.org/ver8.0/ver8_0.pdf), section 10 | AMI syntax/lifecycle and scalar descriptor subset; exact parser sections and limitations are in [AMI inventory](SI_AMI_INVENTORY.md). No external model/code examples copied. |
| [USB-IF USB4 v2 catalog](https://www.usb.org/document-library/usb4r-specification-v20) and [USB-IF PAM3 announcement](https://www.usb.org/sites/default/files/2022-10/USB-IF%20USB%2080Gbps%20Announcement_FINAL_v2.pdf) | Public revision/access metadata and three-level signaling. Full electrical tables/usage terms must be reviewed separately before normative limits are implemented. |
| [PCI-SIG specification catalog](https://pcisig.com/specifications) | Public 7.1 revision metadata (17 September 2026), not a review or redistribution of member specifications or a qualified receiver. Normative access/use restrictions require review before implementation. |
| [MIPI current specifications](https://www.mipi.org/current-specifications) | Public DPI/DPI-2 identities; normative pixel timing, voltage and receiver requirements remain separately supplied/authorized. |
| [VESA DisplayPort FAQ](https://www.displayport.org/faq/) | Public current 2.1b context; not a normative electrical compliance-mask source. |
| [HDMI specification access](https://www.hdmi.org/spec/) and [2.2 overview](https://www.hdmi.org/spec/hdmi2) | Public version/access and licensing boundary; adopter-only specifications/CTS are not bundled or fabricated. |
| [PXI Systems Alliance](https://pxisa.org/) and [JEDEC catalog](https://www.jedec.org/standards-documents) | Specification authorities; exact revision and complete normative content remain required inputs. JEDEC access was blocked during this review. |
| [Design and Verification of Wired Channels Beyond 100 Gbps](https://doi.org/10.1109/TSIPI.2025.3557371), 2025 | Publisher abstract/metadata only were accessible. Candidate research for later full review, not an implemented or qualified method. |

Novelty and citation count do not establish accuracy. Established governing
mathematics and independently constructed oracles remain the baseline; newer
methods must demonstrate better measured performance at the same accuracy and
resource limits. No public overview is used to invent a compliance mask.

## Release boundary

This SI increment follows the already built 0.4.0-alpha.1 preview described in
[coupling feedback](validation/COUPLING_FEEDBACK_20261023.md). A later coherent
standalone worker now runs generic PAM3, with source/schema/runtime checks in
[the SI execution record](validation/SI_EXECUTION_20261023.md). This is not
evidence that the earlier installer contains these additions. Repeat the
installer layer before distributing a new desktop release. The earlier
failed full diagnostic run, optional/hardware coverage, clean-machine/platform
qualification, source/native parity and human numerical review remain open.
