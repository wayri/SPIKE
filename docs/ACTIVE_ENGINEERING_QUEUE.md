<!-- SPDX-License-Identifier: Apache-2.0 -->
# Active engineering queue

The source [parallel worker manager](PARALLEL_WORKER_MANAGER.md) now implements
bounded independent local/remote jobs and explicit mutual-TLS enrollment.
Large-scale single-solve decomposition, additional GPU backends, automatic
certificate pairing and native remote enrollment remain open acceptance work.

Updated 2026-10-09. This records requested follow-on work, not implemented
capabilities. The bounded PI converter/return/capacitor tools are integrated.
The current [capability audit](CAPABILITY_ACCEPTANCE_20261009.md) records the
implemented portion and remaining acceptance checks. Finish active integration
before returning to unrelated queued work, per the user's sequencing instruction.

| Requested work | Required acceptance evidence |
| --- | --- |
| OpenInverter demonstration | Select a specific board/converter and revision from the supplied OpenInverter project, establish licenses, declare operating conditions, and retain reproducible input/result artifacts. The main wiki URL alone is not an electrical study. |
| Closed-loop transient DC/DC SPICE and electrothermal | Run an actual controller/converter model with internal SPICE or ngspice; explicitly map device/PCB losses and temperature feedback; verify energy, timestep and coupling convergence. Review C/C++ and Verilog model integration boundaries. Expose the same workflow from PI and Thermal. |
| Bidirectional PI/SI/EM/thermal coupling | Define electrical/magnetic field transfer and feedback, static and time-varying applicability, occurrence-scoped interboard interactions and honest reduced/full-field status; compare against established solver oracles. |
| Stronger tetrahedral and automatic mesh sizing | Geometry/material/interface preservation, element quality gates, error-driven refinement, memory limits and demonstrable solution convergence on boards, components and STEP assemblies. |
| Unified transient viewer | Returned correlated PI/SI/EM/thermal time frames, viewport run/pause/stop, simulation-time playback and live updates, bounded retention and documented GIF/video codec export. |
| EMerge and simplified thermal references | Inspect the supplied [EMerge transient video](https://www.youtube.com/watch?v=OJCembb8SfI) and [FloTHERM reference video](https://www.youtube.com/watch?v=samd0gbBEAQ); support actual returned extension histories in the viewport and simpler geometry/material/boundary/result workflows. Video fetching was unavailable during PI integration; no frame-specific conclusions have been verified. |
| Viewport performance | Profile real single/multiboard assemblies; preserve interboard/harness identity; cull out-of-view objects, reduce obscured detail, and reuse bounded geometry/GPU caches with fast restoration. Verify visuals and input latency. |
| Harness field coupling | Explicit wire/splice authoring, selected-wire DC, uniform SI and supplied-RLGC branched multiconductor networks are implemented; see [harness engineering](HARNESS_ENGINEERING.md). A bounded straight round-wire/ideal-plane geometry extractor has independent checks. General shield/twist/bend extraction and full-wave radiation remain open. |
| Parallel worker manager | Local multicore scheduling and trusted remote runtime pools with a GUI coordinator, resource admission, cancellation/recovery and result provenance. Benchmark supported Intel/AMD CPU and NVIDIA/AMD/Intel GPU paths; do not promise acceleration for unsupported kernels. |
| Windows release and demonstrations | Retain reproducible transient thermal, multiboard PI and SI demonstrations; complete numerical human review and packaging/upgrade/offline checks before publication/installation. |

Each workstream needs implementation and actual evidence before it changes
`SOLVER_STATUS.md`. Pending requests do not enable solver capability flags.

## Viewport and thermal workflow acceptance

The supplied video references express the requested experience. Their frames
were not accessible during this integration, so the following requirements
come from the user's stated request rather than a verified video inspection.

- Present supported EMerge operations in EM setup with distinct implemented,
  unavailable and planned states. Admit returned histories with explicit units,
  timestamps, source geometry and board occurrence identity before playback.
- Display transient fields in the main viewport, aligned with the originating
  board or assembly. Run/pause/stop controls live in a reserved viewport row;
  minimized controls restore from the bottom tool shelf without occupying the
  notification area. An optional chamber changes visualization independently
  of result availability.
- Keep live solver progress separate from simulated-time playback. Bound frame
  memory, handle missing or failed frames explicitly, and preserve provenance
  when exporting a GIF or video.
- Organize thermal setup as geometry, materials and contacts, loads and cooling,
  mesh, run, and results. Offer concise common-case controls with advanced
  settings available on demand. Include boards, components and mechanical
  structures; show which conduction, convection, radiation or airflow models
  the selected solver actually supports.
- Verify native wide and narrow layouts, retained project reopen, occurrence
  alignment, cancellation and recovery with actual solver output. A styled
  interface or synthesized animation does not establish solver capability.
