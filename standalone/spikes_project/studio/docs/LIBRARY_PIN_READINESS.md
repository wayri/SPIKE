# Pin-complete library readiness

The browser now previews numbered and named generic interfaces for all digital archetypes, ADC/DACs, op-amps, comparators, Schmitt blocks, level translators and isolation amplifiers. Pins have explicit input/output/power roles; converter bits appear individually. Isolated interfaces retain separate supplies and grounds. These logical numbers are NOT manufacturer package numbers.

Existing circuit-ready passive/source recipes retain their exact model pin names with visible terminal numbering. Digital interfaces remain equation-bench-only: a power pin in this preview does not add supply-dependent circuit behavior. Insertion remains disabled for those entries.

Still required before declaring an actual IC ready to use:

- Manufacturer, exact part and package, revision and authoritative pinout evidence.
- All numbered/named power, signal, enable/reset, exposed-pad, NC and reserved pins, with electrical roles and active-low notation.
- Explicit symbol-pin to model-terminal mapping; multi-unit power sections and no silently omitted supplies.
- Redistributable executable model with supply dependence, timing and supported analysis declarations.
- Tests for pin completeness, power-up/down, unpowered I/O and claimed functional behavior.

The current 500 digital presets are parameter variants of 10 generic archetypes, not 500 qualified manufacturer ICs. Complete package symbols and ready-to-run manufacturer IC models are not delivered by the preview change.
