# ADR 0040: Native circuit and retained volume electrothermal coupling

Status: Implemented, experimental; numerical release requires human review.

## Decision

Couple occurrence-scoped native PI DC or SI single-frequency linear MNA to
retained tetra thermal volumes through explicit exhaustive resistor loss
bindings. Keep the original assembly identity separate from the thermal-only
derived assembly, which removes only completely represented electrical links.
Select the internal thermal kernel or separately installed CalculiX at each
fixed-point iteration. Both unrelaxed temperature and power defects must pass.

Store setup and actual results in a dedicated `assembly_volume_electrothermal`
analysis record. Offline admission verifies original identities, circuit
residuals, loss coverage, derived thermal inputs and convergence evidence;
manifest-bound project writes preserve unique model artifacts. Preparation,
execution, integrity admission and physical qualification remain distinct.

## Consequences

The UI and MCP call bounded worker methods; neither implements numerical
physics. Thermal link authoring derives conductance from reviewed total
resistance and matching triangle area. No nearest-face welding, inferred
component thermal resistance or implicit same-name net joining is introduced.

SI heating is steady sinusoidal average dissipation. Ideal sources and reactive
elements have no inferred device loss. Spatial convergence and supplied model
quality remain separate requirements; CalculiX global thermal balance is
unavailable. See [equations and independent analytical oracles](../MULTIBOARD_VOLUME_ELECTROTHERMAL.md).

## Bounded native PWM follow-up, 2026-10-09

The distinct `spike/pwm-electrothermal-request/v1` and result contracts execute
a native persistent synchronous behavioral-switch buck with sampled PI and
winding-only lumped transient thermal feedback. They do not change the steady
volume coupling contract above. Orchestration belongs to
`pwm_electrothermal.py`; SPikes retains the numerical MNA/thermal implementation.
Results retain explicit external switch/load heat, numerical dissipation,
cycle frames and build-bound deterministic replay checkpoints. No arbitrary
vendor model or serialized native-memory loading is admitted. See the
[reference qualification and validity boundary](../SOURCED_POWER_QUALIFICATION.md#actual-native-pwm-with-winding-thermal-feedback-2026-10-09).
