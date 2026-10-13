# ADR 0069: sourced parts, curve drafts and explicit wire-model lowering

Date: 2026-10-12. Status: source increment; not release-qualified.

The Qt-free standalone Studio keeps original source/net identity independent of
presentation. Manufacturer records use `spikes/manufacturer-parts/v1` and retain
exact identity, nominal/rating units, provenance and model readiness. Imported
vendor source is review-only; generic presets, ideal nominal recipes, fitted DC
drafts and qualified device models are distinct states. Counts never imply
manufacturer-model qualification.

Offline NMOS fitting is owned by the numerical Python service, not wx event
handlers, with bounded CSV intake/worker execution and explicit reviewed export.
The current fit has a strict reduced-order forward DC applicability envelope.

Explicit `spikes/wire-rlc/v1` data binds stable wire IDs to the exact project/source
hash. Only supported leaf-edge R/L + endpoint-C networks lower into run snapshots;
saved symbols stay unchanged. The run retains actual pin-node mapping/provenance.
Unadmitted return/branch/distributed topology fails closed. Extraction geometry,
PCB mapping and external plugin execution are not inferred from wire coordinates.

Live source-symbol controls use the same native-step session queue as dashboard
controls. Captured-limit indications are presentation, not physical damage laws.
Recorded, live simulation and disconnected hardware states remain explicit.

Public workflow, derivative/fit limits, import policies and current evidence:
[sourced-parts workbench](../SPIKES_SOURCED_PARTS_WORKBENCH.md). The existing
standalone wx application boundary remains; no Qt dependency or desktop-wide
migration is introduced. Installed app/packaging acceptance and numerical human
review remain separate gates.
