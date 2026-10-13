# SPIKES initial state, temperature, and controlled sources

This is a bounded owned-engine workflow, not full SPICE compatibility. The
parser is `python/spikes/netlist.py`; native state execution remains in the C++
transient kernel. No new numerical integration or device model is introduced.

## Capacitor-state `.ic`

The native parser (`parse_netlist(..., native_extensions=True)`) accepts one
top-level `.ic` directive with up to 4096 `V(node)=value` assignments and a
`.tran ... UIC` analysis. For example:

```spice
R1 out 0 1k
C1 out 0 1u
.ic V(out)=3
.tran 10u 1m UIC
.end
```

Run with the native CLI and an explicitly installed owned library:

```powershell
python -m python.spikes native-run initial.cir --library PATH_TO_SPIKES_DLL --probe "V(out)"
```

The parser lowers capacitor state in volts as
`initial_voltage = V(positive_node) - V(negative_node)`. Only node `0` is
implicitly zero. If either non-ground terminal of an affected capacitor lacks
an assignment, parsing fails instead of guessing its initial voltage.
An assignment to a node that is not used by any capacitor fails too.

Inline capacitor `IC=value` takes precedence over `.ic`, including explicit
`IC=0`; this also holds in flattened subcircuits. Such a capacitor does not need
both `.ic` terminal assignments because its inline state is authoritative.
Case-insensitive node names and explicitly flattened node names such as
`V(x1:internal)=2` are accepted. `.ic` inside a subcircuit definition is not.
Duplicate assignments, nonzero reference-node voltage, malformed expressions,
nonfinite values, repeated `.ic`, and unsupported assignments fail with a
source-located `SPIKES_NETLIST_IC_*` diagnostic.

Values may use finite SPICE numeric literals or brace expressions involving
earlier top-level parameters. Parameter dependencies are reevaluated for each
`.step param` variant before lowering its state. The resulting state is stored
in the existing `CircuitElement.initial_condition` field; it survives project
serialization and uses the existing native ABI, with no new solver field.

This is capacitor-state initialization, **not** arbitrary node initialization
or a constrained operating-point solve. Absolute common-mode state, transistor
charge initialization, and node guesses are not established by this lowering.
`.ic` without `UIC` is rejected because the normal operating-point initialization
would overwrite capacitor state. The reference-runner parser route rejects
`.ic`; use the native route. For inductor state, use the already supported
element syntax `L1 a 0 1m IC=2m` (amperes, positive from the positive terminal to
the negative terminal); `.ic I(L1)=...` is not introduced. Native UIC results
start at the first accepted integration step, not an invented time-zero solve.

## Temperature

The existing `.temp VALUE` directive accepts one finite temperature in degrees
Celsius, greater than -273.15 and at most 2000. It may appear once at top level;
the default is 27 C. Earlier parameter expressions are accepted and evaluated
at the directive. The circuit contract retains `temperature_c`, and diode
models receive `temperature_k = temperature_c + 273.15`.

The focused native test establishes the diode thermal-voltage term
`k*T/q` at 125 C with declared constant saturation current and ideality factor.
This is not complete temperature-dependent manufacturer-model qualification:
the directive does not supply missing saturation-current, resistance, or other
device temperature coefficients. Non-default temperature for the current
semiconductor-node bindings (including Q/M models) remains explicitly rejected.

Multiple `.temp` values and `.step temp` are unsupported. They are not rewritten
as ordinary parameter steps because the step-variant contract does not carry
an independent circuit temperature. For an existing, separate linear R/L/C
coefficient study, use `temp-sweep` with explicit element coefficients. That
reference-runner workflow is not semiconductor temperature simulation.

## Behavioral and controlled sources

There is no `.bc` directive. B/E/F/G/H are existing element forms:

| Form | Meaning | Gain units |
| --- | --- | --- |
| `E1 out 0 in 0 3` | Voltage-controlled voltage source | V/V |
| `G1 out 0 in 0 1m` | Voltage-controlled current source | A/V |
| `F1 out 0 V1 3` | Current-controlled current source | A/A |
| `H1 out 0 V1 1k` | Current-controlled voltage source | V/A |
| `B1 out 0 V={3*V(in)}` | Behavioral voltage source | Expression returns V |
| `B1 out 0 I={1m*V(in)}` | Behavioral current source | Expression returns A |

F/H control current follows the controlling voltage-source branch orientation.
The parser may lower constant or proven single-signal, zero-offset affine B
expressions to native independent/controlled sources. Other admitted B
expressions retain their behavioral form. The focused native checks cover the
four controlled-source classes, affine voltage/current B expressions, and a
nonlinear polynomial B voltage source in operating point. They do not establish
all expression/model/analysis combinations. Native AC remains separately gated;
unsupported behavioral operators such as `ddt` remain explicit parser errors.

## Existing Monte Carlo scope

`monte-carlo` and `python.spikes.sweeps.run_monte_carlo` already provide seeded,
deterministic relative variations of nonzero element values in linear R/L/C/V/I
decks. Distributions are uniform or clipped normal with the tolerance denoting
three sigma for the latter. The contract records seed, parameters, case results,
and the SHA-256 counter random mapping. Bounds are 256 cases, 16 unique variation
targets, and 250000 aggregate solve points. This path uses independent
reference-runner cases; it is not a native nonlinear-device statistical model,
not a `.mc` deck parser, and not a device mismatch/correlation implementation.

## Verification and limits

`tests/python/test_spikes_initial_directives.py` uses original minimal fixtures
and independently authored oracles. The RC oracle is backward Euler
`V_n = 3/(1 + dt/(R*C))^n`, with R=1000 ohm, C=1 microfarad, and dt=10
microseconds. It asserts 1e-10 V agreement and compares the final sample with
the analytical exponential within 5e-4 V. Identical `.ic` and inline `IC=` decks
must return identical native data. Source tests use direct KCL and gain equations
with 1e-9 V tolerance. The diode oracle uses declared constant Is=1e-12 A,
I=1e-3 A, n=1, T=398.15 K and `V=(k*T/q)*ln(1+I/Is)` within 1e-9 V.

The tests also cover rejection, polarity, explicit zero precedence, hierarchy,
parameter steps, and project round-trip. Native tests skip only when the
configured DLL is absent; they are not parser-only evidence. Reproduce with:

```powershell
python -m unittest tests.python.test_spikes_initial_directives tests.python.test_spikes_spice3_wave7 tests.python.test_spikes_sweeps tests.python.test_spikes_transient_controls -v
```

Set `SPIKES_TEST_NATIVE_LIBRARY` to select the tested native library. These
checks are bounded local integration evidence, not general circuit qualification
or a replacement for knowledgeable numerical review before release.
