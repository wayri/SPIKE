# Model fidelity and inherited policies

Open **Model fidelity / preflight** in the simulation manager or the corresponding
button in component properties. Select the schematic, a flattened subsheet instance
path, or a component. Apply saves one undoable scope change. Remove override restores
inheritance. Existing documents default to `source`, preserving their explicit deck.

Resolution order is schematic → nested subsheets → component. The first enforced
parent locks descendants, with its scope displayed. Existing child overrides are
retained but ignored while locked. Unsupported tiers are disabled, not substituted.
Source means the explicit deck model, not a quality guarantee. Available explicit
tiers currently describe ideal RLC/sources and simplified static diode/switch models.
They do not transform one device family into a different physical model.

Preflight blocks missing scope targets, unavailable tiers, unsupported selected-tier
analyses and required implicit parasitics without a backend binding. The read-only
report lists exclusions, pins, source-model description and qualification boundaries.
Explicit parasitic components in the deck remain active. Declaring ESR in the policy
does not magically add an ESR resistor: until a binding exists it blocks the run.

Batch, continuous and sequence runs resolve their effective source. Frequency runs
also check policy; source mode retains existing backend validation. Result provenance
contains the resolved policy, exact effective source and SHA-256. Reproducibility
also requires preserving external libraries and the engine build; the source hash is
not a hash of all external dependencies.

## Beta.5 capacitor package binding and previews

Select an individual top-level capacitor in the fidelity dialog. In source tier,
enter ESR in ohms, ESL in henries and/or leakage resistance in ohms; blank disables
that element. Positive finite SI numbers are required. Apply scope refreshes the
graph. RLC components show an equivalent circuit and analytical impedance magnitude
from 1 Hz to 100 MHz. This display range is not a physical validity range.

Runs expand capacitor packages into series ESR/ESL followed by the original capacitor,
with leakage across the external terminals. The original schematic source is unchanged.
Results retain both original and expanded source. I(C) and P(C) refer to the ideal
capacitor inside the package, not total package current/dissipation; generated R/L
elements have separate result signals. Explicit parasitics already in the circuit
are not detected or removed: avoid double counting.

Qualification is limited to analytical impedance identities and native DC leakage
checks, not manufacturer measurements, temperature dependence, dielectric absorption,
nonlinear capacitance or broadband package extraction. Unsupported part families and
hierarchical parasitic expansion remain disabled. Detailed vendor tiers remain unavailable.

Remaining work: additional graphical device previews and characteristic curves,
qualified detailed model registry, structured validity envelopes, supported implicit
parasitic stamping beyond the capacitor binding, and broader device-specific analysis qualification.

Source update: the preview now also draws native static diode/smooth-switch/source
symbols and plots parameter-derived diode I–V, switch resistance/control-voltage,
and DC/PULSE/PWL waveforms. See MODEL_QUALIFICATION_STATUS.md for per-family evidence
and the native-runner limitations. These source changes require a new package build
before they appear in an already installed beta.5.
