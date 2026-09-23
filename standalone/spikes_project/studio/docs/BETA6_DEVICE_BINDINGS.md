# Beta.6 device bindings (Windows engineering preview)

## Berkeley BSIM

The owned C++ solver now receives the pinned Berkeley BSIM-BULK 107.2.1 and
BSIM-CMG 112.1.0 OSDI modules through the Studio runner. No Level-1 substitution
is used. Module digests are checked before loading native code. License, notices
and original Verilog-A sources are bundled. This is trusted in-process execution,
not a hostile-code sandbox.

```spice
Vd d 0 1
Vg g 0 PULSE(0 1 1n 1n 1n 10n 20n)
M1 d g 0 0 core
.model core BSIMBULK()
.tran 100p 4n
.end
```

Use `BSIMCMG()` for CMG. Four-terminal cards bind D/G/S/B (CMG's fourth terminal
is E). The fifth Berkeley temperature-rise terminal is grounded: these cards are
explicitly isothermal at 300.15 K. Model parameters are checked against the
module's numeric parameter metadata; W/L instance geometry is supported when the
selected module declares it. Unsupported names/types are errors. These names do
not imply support for BSIM3/BSIM4 LEVEL aliases, process-card binning, or arbitrary
foundry dialects. Select backward Euler for transient OSDI execution; other
integration methods remain unsupported. No new Studio AC/noise binding is claimed.

The release fixes collapsed-node topology in native registration, avoiding
spurious floating unknowns. The regression test exercises full DC and transient
circuits for both modules, not only isolated callbacks.

## Generic IGBT and thyristor library

`examples/compact_charge/generic_power_devices.lib` contains parameterized
`SPK_IGBT C G E` and `SPK_SCR A G K` subcircuits. Include the file or paste its
definitions into a deck and instantiate with X. Their B sources execute in the
native C++ Newton solver; RC state networks use native transient integration.

SPK_IGBT exposes threshold, gate span, forward knee, on/off resistance, a state
relaxation time and gate/Miller capacitances. SPK_SCR exposes gate voltage,
forward knee, on/off resistance, holding-current threshold, transition width,
state time and gate resistance. Parameters require physically sensible positive
values; the library does not provide a complete parameter-validity checker.

These are generic behavioral macromodels, NOT production IGBT/SCR compact-model
bindings. The internal state is a dimensionless proxy, not physical stored
charge. Tail decay and gate capacitance, SCR latching and zero-voltage commutation
are regression tested. Reverse recovery, avalanche, breakdown, electrothermal
coupling, dv/dt triggering, SOA and manufacturer accuracy are not qualified.

## Release boundary

This remains an unsigned engineering preview, not production/safety-certified
software. Device-family tests do not qualify manufacturer parts. Production
IGBT/thyristor compact models and model-specific manufacturer validation remain
open. Linux BSIM binaries are not supplied by this Windows release.
