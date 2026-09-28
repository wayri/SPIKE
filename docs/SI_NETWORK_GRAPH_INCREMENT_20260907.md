<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Coupled multiboard SI increment — 2026-09-07

## Available now

The SI workflow accepts `channel.kind = "network_graph"`. Each digest-bound
RLGC or Touchstone leaf declares its owner and reference planes. Explicit
paired internal ports are eliminated in wave coordinates; ordered external
ports feed the existing source/receiver, loaded transfer, PRBS, eye, TDR,
noise and Touchstone workflow. Coupled four-port leaves retain their coupling.
This replaces the previous serial-two-port-only boundary, but does not infer
physical junctions, returns, connector models or cross-board fields.

Limits: 16 leaves, 64 total ports, 2–16 external ports, 8193 frequency samples,
8 MiB control and bounded dense work. Grids must match exactly. Hash,
reference-plane, duplicate-terminal, singular-feedback and resource failures
are rejected. A plane identity is an assertion, not a CAD verification.

Optional `resonance_requests` entries select an edited-channel port, explicit
positive frequency bounds and `series_rlc` or `parallel_rlc`. Results in
`resonance_fits` qualify only that declared equivalent circuit. They require
positive R/L/C, low complex fit residual, stable split-band identification and
independently resolved half-power bandwidth agreement. No automatic multimode
or physical pole/Q qualification is claimed. All other channel ports are
matched; workflow source/receiver/passive loads are **not** used for this fit.

The workbench JSON setup accepts both additions, and its results expose
provenance/port mapping and fit diagnostics. Original algorithms implement
wave elimination and RLC mathematics; no third-party solver code was copied.
The RLC identities can be checked against
[MIT 6.101 resonance and bandwidth notes](https://web.mit.edu/6.101/www/s2019/handouts/L02_4.pdf).
These are established mathematical references, not a claim of new research.

## Executed evidence

- `build/si-network-graph-20260907/`: coupled two-board four-port chain versus
  the equivalent uniform line, maximum complex S error 1.51e-15; internal
  elimination residual 1.86e-16. Includes channel, loaded example and Touchstone.
- `build/si-network-graph-workflow-20260907/`: executable request and actual
  source-to-receiver result. Against the equivalent line, loaded transfer error
  was 5.40e-16 and PRBS waveform error 5.56e-16 V. NEXT/FEXT matched the standalone
  loaded example. Reproduce with `python scripts/benchmark_si_network_graph_workflow.py
  --output build/graph-workflow-new` (fresh directory required).
- Focused regression: 94 Python tests with warnings treated as errors,
  including workflow graph/schema, loading, waveform and resonance integration.
- `build/si-resonance-workflow-example-20260907/`: actual workflow recovered
  the analytical 10 MHz, Q=10 series RLC, with Q relative fit error 7.39e-13;
  the independent sampled bandwidth Q differed by 0.0537%, within its 5% gate.
  Run `python scripts/run_si_resonance_example.py --output build/rlc-new-run`
  with a fresh directory to reproduce.
- SI workflow/crosstalk renderer assertions, full TypeScript check and
  architecture guard passed. These are not visual inspection or packaging tests.
- `build/cambridge-measured-si-20260907/`: four original 1601-point two-port
  measurements admitted and analyzed, with source attribution and hash records.
  The data remains CC BY 4.0, not the application's MIT license.
  Two additional admission tests passed. See
  [measured SI reproduction and limitations](MEASURED_SI_CAMBRIDGE.md).

## Boundaries that remain open

The Cambridge two-wire fixture is measured data processing, **not** correlation
of SPIKE-extracted fields against hardware. Its missing near-end pair data
must not be synthesized into a complete four-port model. Exact launch geometry
and quantitative calibration uncertainty are absent from the admitted metadata.

Cross-board field extraction still requires a world-coordinate assembly mesh
that preserves each board's dielectric interfaces and the intervening air,
explicit return/terminal/port definitions, coupled field execution, and mesh,
boundary and independent-reference convergence. Merging existing single-board
bounding-box dielectrics would incorrectly fill air and is not enabled.

General multimode resonance/Q requires a separate pole or eigenmode workflow,
loading-aware definitions, adaptive frequency convergence and uncertainty
evidence. Single-RLC fit acceptance must not advertise this as completed.

Browser URL policy blocked inspection of local HTML exports. No alternate URL,
browser, proxy or screenshot workaround was used. Numerical exports and source
assertions do not close the visual acceptance item. Commercial-tool parity,
general geometry correlation and production qualification remain unclaimed.
