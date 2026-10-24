# ADR0129: Declared EMerge network circuit and resistor-thermal boundary

Accepted for experimental internal APIs, 23 October 2026; numerical human
review remains required before release.

Keep source admission and circuit mapping in EMerge's adapter. Reuse owned
sample validation and solve small circuit connections directly in waves, not
potentially singular S-to-Z. Require design/case/script identity, explicit
common-real RMS convention, all terminal pairs and reference planes. Preserve
source status. Only known external series-resistor heat is mapped conservatively
to existing thermal cells. EM port deficit may be radiation, not heat.

No inferred PCB heat footprint, field calibration, live SPICE execution, added
dependency, worker/GUI registration or capability promotion. Native/HPC owners
remain unchanged. See [derivation and evidence](../EMERGE_COSIMULATION.md).

Subsequent owner-authorized release integration adds explicit owned-worker and
CLI routes plus draft-only desktop export and guarded Python Workspace
templates, documented in [the integration record](../validation/EMERGE_RELEASE_INTEGRATION_20261023.md).
The original numerical/qualification limits remain unchanged; this supersedes
only the initial decision to keep these APIs in-process.
