<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0136: Explicit retained geometry propulsion ports

Date: 23 October 2026. Status: experimental source integration. Real-source
actual-air load convergence, completed hardware example, GUI observation and
knowledgeable numerical release review remain separate gates.

The synthetic FEM/BEM benchmark cannot represent the real-source workstream.
The geometry loop has its own result contract and imports an immutable periodic
quadratic coenergy table and retained quasi-steady CFD-anchor table. A shared
application boundary checks bounded parameters, source hashes, balanced initial
currents, thermal input expansion and admissible speed/current envelopes. CLI
and explicit worker run use that same boundary. Only the existing fixed built-in
demonstration C controller is compiled; no script/library path or injected source
is accepted. Coenergy, discrete-gradient shaft exchange and thermal resistance
feedback use their separately derived numerical owners, not new transport math.

`propulsion_pod_geometry_run.py` owns bounded preparation/execution;
`service_propulsion_pod_geometry.py` owns capabilities/validate/run routes. The
new run method is classified heavy in both frontend and thin host, preserving
the established process/cancellation boundary. Source/table admission checks
representation and identity, never the truth of convergence evidence. Runtime
failure refuses a completed result. An optional unavailable Studio compiler
fails explicitly; no fallback motor, controller or BEM load is substituted.

`spike/geometry-propulsion-ui-study/v1` dispatches separately from the synthetic
capture. The existing project study slot is retained for compatibility. Native
packages retain exact effective setup, source tables and captured result; copy
without results retains source tables and removes all derived histories/fields.
The GUI can rerun the retained port loop through the worker. This does not solve
new spatial FEM/CFD fields on each GUI run. Source-bound offline reconstruction
may attach actual P2/Fourier fields at saved accepted currents/angles. Replay
shows only retained states, with endpoint and preceding-interval data distinct.
Geometry result objects replace the previous result atomically on native save;
generic preservation of unknown project fields must not resurrect omitted old
spatial snapshots or reconstruction receipts inside a new run.

Packaging preserves native source members and colocates exact KiCad boards and
available original project/schematic/library companions. File inventory and
native reopening do not imply numerical qualification or GUI visual acceptance.
Tests include malformed/tampered captures, actual compiled-controller worker
output crossing the real UI parser, and rejection of stale/source-mismatched
data. No computer use is part of this implementation/verification workstream.
