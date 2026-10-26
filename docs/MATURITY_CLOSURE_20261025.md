# Finite maturity closure campaign

Owner priorities recorded 25 October 2026: full-board extraction, assembly
multiphysics, protocol compliance, general vendor models, measurement correlation
and release qualification. First protocol targets selected: **USB 3.2 Gen 1
(5 Gb/s)** and **10GBASE-KR**. Other protocols follow after these finite targets.

## What can actually close

| Workstream | Checkable closure evidence | Current boundary / next work |
| --- | --- | --- |
| Full-board extraction | Named source revision; all admitted copper/pads/vias/contacts accounted for; explicit unsupported geometry; independent mesh/topology and refinement checks under resource limits | Existing supported geometry remains bounded. Close a named board/rail corpus first; arbitrary CAD cannot be inferred from one successful case. Existing PI heat/p99 and large-mesh failures remain open. |
| Assembly multiphysics | A named assembly with explicit connector/thermal/contact identities; individually converged domains; conserved transferred power/heat; coupled residual and refinement results | Build one electrical-to-thermal assembly benchmark with a retained source, then extend verified directions. Placement visualization is not cross-board coupling. |
| USB 3.2 Gen 1 | Exact applicable test revision, device role/connector/test points and fixture; transmitter/receiver/channel cases with normative limits and independent expected results | Electrical, link/interoperability and cable/connector testing are separate scopes. Do not substitute an eye preset for certification. |
| 10GBASE-KR | Exact IEEE revision/clauses and fixtures; transmitter, channel, receiver/equalization, CDR, jitter/noise, training and independent correlation | Existing evidence inventory is preparatory and cannot claim protocol compliance. Review normative requirements before implementing limits. |
| Vendor models | Explicit supported grammar and model types; driver and Input-sink I/V, clamps, C/package, switching fixtures; rejected-feature corpus; independent nonlinear and runtime checks | This increment adds a bounded classic IBIS path. General import/registration remains available. AMI runtime, power-aware and unsupported model types stay separate. |
| SI spatial noise | Revision-bound returned victim-voltage samples and independently supplied/solved E samples; exact units/probes; malformed/stale-data rejection; observed native viewport evidence | This increment adds sampled-data admission and main 3D rendering. No invented spatial field from S-parameters. Native visual and multi-board transformed acceptance remain open. |
| Measurement correlation | Licensed measured data with exact geometry, calibration, reference plane, uncertainty and predeclared numerical error criteria; executed comparisons | Owner confirmed no admitted measured corpus. Metadata manifest validity alone is not correlation; synthetic/reference solutions cannot replace measurements. |
| Final release qualification | Complete required source checks, exact artifact hashes, clean installed lifecycle on each target, source/artifact identity and knowledgeable human numerical approval | Shared full-suite interruption, installed/native acceptance and human review remain open. A disclaimer does not close these gates. |

## First execution order

1. Finish the bounded IBIS and sampled SI workflow, run independent oracles and
   failure cases, then exercise native controls and waveform/field probes.
2. Freeze one board extraction and one coupled assembly benchmark, including
   resource/error budgets before extending geometry coverage. Repair failing
   numerical acceptance criteria without weakening the criteria.
3. Implement separately versioned electrical test cases for the two selected
   protocols, with traceable limits and reference outcomes. Keep per-test
   pass/fail separate from full protocol/certification claims.
4. Admit real measured evidence when available, execute correlation, then run
   final platform/install qualification on the exact source and artifact set.

The [IBIS and spatial workflow](SI_IBIS_SPATIAL_WORKFLOW.md) describes this
increment. The existing [SI08 finite checklist](SI08_FAMILY_CLOSURE.md),
[measurement evidence policy](CORRELATION_EVIDENCE.md) and
[solver status](SOLVER_STATUS.md) remain authoritative for their dated gates.

## Primary protocol source ledger

The [USB-IF USB 3.2 index](https://usb.org/usb-32), checked 25 October 2026,
lists electrical CTS revision 1.8 dated 30 June 2026, with separate link,
interoperability and cable/connector procedures. Only the index was reviewed in
this increment; no CTS thresholds are represented as implemented or verified.

The public [IEEE task-group contribution](https://www.ieee802.org/3/az/public/nov09/Pillai_01_1109.pdf)
mentions 10.3125 GBd and Clause 72. It is a historical contribution, **not the
normative standard** and not a source for compliance limits. The exact normative
IEEE revision and applicable procedures must be reviewed before a KR compliance
engine can close. The selected protocol name does not grant source or fixture
redistribution rights.
