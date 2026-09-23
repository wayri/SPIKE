# Signal Integrity Network Workbench

## Decision

SPIKE implements its own permissively licensed network-data layer and treats
geometry extraction, field solving, circuit solving, and network post-processing
as separate plugin boundaries.

The Nubis Communications SignalIntegrity project is a useful behavioral
reference for interconnected S-parameter blocks, de-embedding, virtual probing,
calibration, waveform processing, and eye-diagram workflows. Its implementation
is GPL-3.0-or-later, so SPIKE does not copy, vendor, import, or link that code
into the MIT/open-core core.

SignalIntegrity may be supported later as an optional external-process adapter.
That adapter must exchange files or versioned JSON through SPIKE's solver
process boundary and preserve the upstream license and notices. SPIKE's native
implementation remains clean-room: public behavior may define acceptance
tests, while algorithms come from independently written standard mathematics,
primary research, and SPIKE-owned fixtures. Upstream implementation code is not
copied, translated, vendored, imported, or linked into SPIKE.

References:

- https://github.com/Nubis-Communications/SignalIntegrity
- https://github.com/Nubis-Communications/SignalIntegrity/blob/master/LICENSE.txt

## Implemented foundation

`python/spike_core/sparameters.py` provides:

- Touchstone 1 full-matrix parsing for RI, MA, and DB data.
- Touchstone 2 keyword parsing for port count, reference impedance, and full
  network data sections.
- S, Z, and Y ingestion.
- S-to-Z, Z-to-S, and S-to-Y conversion for real positive per-port references.
- Reference-impedance renormalization.
- Adjacent-pair single-ended to mixed-mode conversion.
- Passivity checks using the maximum singular value.
- Reciprocity checks.
- S-parameter magnitude and unwrapped phase traces.
- S21 group-delay data.
- Port-1 matched-termination input impedance.
- Touchstone export.

The desktop HF/SI ribbon now opens an offline S-parameter workbench with file
import, port-matrix selection, magnitude plotting, point readout, passivity and
reciprocity checks, limitations, and normalized JSON export.

The Channel Tree can also compose a visual source-to-sink path from driver,
channel, connector, cable/harness, termination, and receiver blocks. This is a
setup diagram today. It does not yet bind typed lane/pair/port identities,
IBIS/SPICE/package models, stimulus, probes, or an executable SI run plan, so
persisting the tree is not evidence of a solved channel.

The SI Protocol Suites workbench configures dedicated protocol workflows and
links to both surfaces. A suite is configuration and prerequisite planning, not
a standards-compliance solver.

`python/spike_core/si_channel.py` and `si_coupled_channel.py` provide separate
bounded geometry-derived channel paths. Their strict default admits one
straight constant-width DesignIR v2 track chain or two straight, parallel,
coextensive chains over one simple fully covering reference-zone/homogeneous-
dielectric stack. The explicit `piecewise_planar` mode also admits a connected,
same-layer, constant-width planar route with bends. It records the segment/bend
evidence but treats the route as a cascaded or conservatively averaged uniform
line: it does not model bend discontinuities. A coupled piecewise pair requires
explicit separation/skew tolerances and matched parallel segments, and uses the
conservative minimum separation. The single path emits experimental scalar RLGC
and reciprocal two-port S; the pair uses a sparse 2-D Maxwell-capacitance solve,
C0-derived L, and multiconductor propagation to emit matrix RLGC, four-port S,
and bounded NEXT/FEXT. A selected P/N pair also has an orthonormal mixed-mode
transform, differential two-port, TDR/TDT, and normalized deterministic NRZ
eye. The worker method is
`run_si_uniform_channel` and the CLI command is `si-geometry-channel`. See
[`GEOMETRY_DERIVED_SI_CHANNEL.md`](GEOMETRY_DERIVED_SI_CHANNEL.md) for its exact
admission rules and release gates.

## Capability boundaries

The network workbench does not create electromagnetic results. Network data can
come from:

- SPIKE PEEC 2.5D extraction.
- Future surface MoM or full-wave 3D plugins.
- Measured VNA data.
- Imported commercial-tool data.
- Optional external solver adapters.

An imported file passing structural, passivity, or reciprocity checks is not
proof that the originating model or measurement is physically accurate.

Causality for imported arbitrary network data is intentionally reported as
`not_evaluated`. A defensible check requires explicit policy for DC
extrapolation, frequency resampling, windowing, reference-plane delay removal,
and noise. SPIKE must not silently choose these settings. The bounded uniform
channel instead requires an explicit DC-starting uniform grid and records its
finite-bandwidth, no-window/no-padding/no-de-embedding policy; that explicit
transform is not a general causality qualification.

Consequently, release-grade end-to-end SI cannot currently be run from a
source-to-sink diagram. Numerical SI routes are imported Touchstone inspection
and bounded experimental single/pair geometry channels. The desktop DDR and
SerDes suite presets can launch the S-parameter workbench with net, P/N,
reference, and tolerance selection; it renders bounded native charts and
exports JSON or offline SVG HTML. The selected suite and latest result reopen
from the legacy project analysis payload. This is workflow persistence, not a
typed digest-bound source/sink run plan. These routes do not cover general
coupled layouts, differential/mixed-mode qualification, vias/launches,
source/package/receiver behavior, statistical eyes, or protocol signoff.

## Public workflow acceptance baseline

The public SignalIntegrity project exposes a useful product-level behavioral
benchmark: interconnected circuit and S-parameter-block solving, de-embedding,
virtual probing, network-analyzer calibration, S-parameter viewing, waveform
processing, TDR-oriented workflows, and eye-diagram analysis. SPIKE targets the
same class of user workflow plus PCB/assembly geometry extraction, explicit
resource admission, project provenance, and multi-board coupling.

Parity means independently reproducing observable results within published
tolerances. It does not mean reproducing upstream source structure, code,
tests, artwork, wording, or internal algorithms. Every numerical promotion
requires analytical fixtures, primary-source provenance, an independent solver
or measurement comparison where practical, uncertainty/applicability records,
and a fail-closed capability decision.

## Sequential network-analysis gates

1. Promote the Channel Tree to a typed SI schematic contract: explicit ports,
   directions, differential mates, lanes/bytes/strobes/clocks, references,
   terminations, probes, source/receiver bindings, package persistence, undo,
   and a fail-closed preflight. A persisted graph must compile to an inspectable
   analysis plan.
2. Expose the Python network engine through the worker and complete user-defined
   mixed-mode pairing/reference impedances, Touchstone 2 matrix/noise forms,
   deterministic frequency-grid policy, and diagnostics.
3. Implement the interconnected multi-network engine: N-port interconnection,
   termination, two-port/multiport cascade, hierarchy, variables, model reuse,
   conditioning/error reporting, and analytical circuit/network fixtures.
4. Add fixture/reference-plane processing: renormalization, port transforms,
   de-embedding, causality/conditioning, residuals, calibration provenance, and
   uncertainty. No silent DC extrapolation, resampling, or window selection is
   permitted.
5. Add TDR/TDT/impulse/step conversion, source/channel/receiver convolution,
   and virtual probes with delay/reflection-location fixtures.
6. Add deterministic PRBS and user-defined waveform sources, IBIS/SPICE/package
   model binding, receiver behavior, NRZ/PAM4 eyes, clock recovery, bathtub/BER,
   and jitter/noise/crosstalk decomposition.
7. Connect validated matrix-RLGC/quasi-TEM and later 2.5D/full-wave geometry
   extraction. Validate microstrip, stripline, differential/coupled lines,
   connectors/vias, and measured channels before promoting geometry-derived SI.
8. Enable protocol-specific screening only after the shared stages pass. A
   licensed, revision-specific limit set and applicability evidence are required
   before any protocol compliance claim.

Every increment requires analytical fixtures and round-trip tests before its
capability state can become `validated`.

The bounded single-line, coextensive-pair, and opt-in piecewise-planar slices
are implementation increments inside gate 7, not completion of gates 1 through
8. Their current analytical and structural regressions do not promote general
quasi-TEM, S-parameter, TDR/TDT, eye, crosstalk, DDR, SerDes, or protocol
capabilities.
