# Retained-volume PWM correlation, 2026-10-10

This is bounded synthetic numerical evidence, not release qualification,
representative PCB cooling accuracy, measured hardware correlation, or a
vendor semiconductor model. Knowledgeable human numerical review remains
required before release.

## Independently checkable fixture

The original fixture is a one-cubic-metre insulated mathematical solid split
into six equal-volume tetrahedra. Its conductivity is 2 W/(m K) and its total
heat capacity is 0.01 J/K. These deliberately artificial properties isolate
energy transfer; they are not a proposed physical PCB material. Each of the
four circuit devices (`Rw`, `SH`, `SL`, `Load`) deposits equal fractions into
the six cells. The initial field is uniformly 300 K. Consequently every
committed frame must satisfy

```text
T = 300 K + sum(all accepted physical device energies) / (0.01 J/K).
```

The tests check that identity at every frame to 2e-8 K, not only the endpoint.
They separately assert positive heat from all four devices, the electrical
energy ledger, and that numerical backward-Euler dissipation is not deposited
as physical heat.

The independent switched ODE uses switch-node KCL to eliminate the algebraic
node. With `gh` and `gl` the active high/low switch conductances,

```text
vsw = (Vin*gh - i)/(gh+gl)
L*di/dt = vsw - Rw(T)*i - v
C*dv/dt = i - v/Rload
Cthermal*dT/dt = Rw(T)*i^2 + v^2/Rload
                 + gh*(Vin-vsw)^2 + gl*vsw^2
```

An original event-aligned RK4 implementation advances these equations, with
the same explicitly specified cycle-sampled PI control policy. This oracle
does not call native MNA, the retained thermal kernel, or its matrix assembly.
It does not replace the circuit with an averaged voltage source.

## Actual checks and fixed gates

The run uses 80 PWM cycles at 20 kHz (0.004 s), the existing native
`build-peec-native/spikes_c_api.dll`, and separately installed CalculiX 2.23
at `C:/msys64/ucrt64/bin/ccx.exe`. The executable hash is
`913abf828a2d706f3e8c9da89d7a0eddd68ce817f8dabf1098cb013dfe3f94f6`.
No runtime was installed or rebuilt.

| Check | Actual result | Gate |
| --- | ---: | ---: |
| RK4 endpoint difference, 0.1 versus 0.05 us steps | 2.7534e-14 maximum component difference | <= 1e-7 |
| Native/reference endpoint norm, electrical steps 2, 1, 0.5 us | 0.0142587, 0.00782760, 0.00396956 | each halving improves > 1.5x; finest < 0.05 |
| Inductor-current errors, electrical steps 2, 1, 0.5 us | 0.00667074, 0.00410020, 0.00197444 A | each halving improves > 1.5x; finest < 0.005 A |
| Output-voltage errors, electrical steps 2, 1, 0.5 us | 0.00309807, 0.00148016, 0.000733730 V | each halving improves > 1.5x; finest < 0.002 V |
| Temperature errors, electrical steps 2, 1, 0.5 us | 0.0122153, 0.00650145, 0.00336462 K | each halving improves > 1.5x; finest < 0.005 K |
| Window-size endpoint norms relative to one-cycle windows, sizes 8, 4, 2 at fixed 0.25 us electrical step | 4.88433e-4, 7.78047e-5, 1.53079e-5 | each refinement improves > 2x; coarsest < 0.01 |
| Uniform CalculiX versus coupled temperatures, all 81 frames | 4.69927e-5 K maximum | <= 6e-5 K |
| Nonuniform CalculiX versus independently assembled centroid-capacity oracle | 5.05332e-5 K maximum | <= 6e-5 K |
| Nonuniform SPIKE versus independently assembled exact-P1-capacity oracle | 1.13687e-13 K maximum | <= 1e-8 K |
| Retained two-board/package fresh CalculiX versus new prepared-step history | 0.0114258 K maximum | per-frame 0.05 K + 5% maximum temperature rise |
| Retained two-board/package saved SPIKE versus new prepared-step history | 0 K maximum | <= 1e-8 K |

Endpoint norms scale current by 1 A, voltage by 1 V and temperature by 1 K;
they are dimensionless numerical regression metrics, not a universal physical
error norm. The separate current, voltage, and temperature gates are all
asserted in their physical units; the norm does not substitute for them.
Electrical refinement and thermal-window refinement are separate
sequences. Window refinement compares against the one-cycle numerical result,
not against a claim of an exact spatial or temporal solution.

The uniform CalculiX run replays the actual accepted all-device energy of each
window as its energy-equivalent heat load. Its backward-Euler deck samples the
prescribed right-endpoint powers. This is an independent solid-field history
comparison, not an independently coupled CalculiX circuit calculation.

## Retained PCB/package history

The existing original OCC-meshed fixture under
`.local/transient-thermal-validation/` contains two homogeneous retained PCB
occurrences and one STEP-derived package, with 288 nodes, 737 tetrahedra,
explicit contact and fixed-temperature board boundaries. The new prepared-step
API distributes the fixture's 0.04 W package heat by cell volume and advances
20 steps of 0.05 s, retaining five frames through one second. A fresh actual
CalculiX solve uses that same retained geometry and material setup; its result
passes the standard complete-history and input-identity admission. There is
no remeshing, imported upstream fixture, or modification of the original files.

This test covers prepared energy deposition and thermal history on actual
retained PCB/package meshes. Its heat is the original prescribed package
source, not a PWM-derived package loss, and it does not establish fully coupled
PWM accuracy for this mesh. The saved SPIKE history is a regression reference;
the fresh CalculiX result is the external-solver comparison. Source artifact
hashes, complete frames and per-step energy ledgers are retained separately.

## Nonuniform disagreement is retained

For the original 27-node sine-profile cooling fixture, the actual maximum
SPIKE/CalculiX temperature difference is **0.351567 K**. Cross-solver agreement
is explicitly false. This is not suppressed by a larger comparison tolerance.

The separate original matrix oracles distinguish the two rules:

```text
exact P1 capacity: rho*cp*V*(I + 11^T)/20
centroid capacity: rho*cp*V*11^T/16
```

Each solver matches its corresponding discrete backward-Euler oracle. Uniform
temperature has the same capacity row sum under both rules, explaining why
the uniform transfer case agrees while the nonuniform field does not. This
evidence does not establish interchangeable nonuniform thermal solvers or
general mesh convergence.

## Reproduction and artifacts

```powershell
$env:SPIKE_PWM_TEST_LIBRARY = (Resolve-Path build-peec-native/spikes_c_api.dll).Path
.venv/Scripts/python.exe -m unittest tests.python.test_pwm_volume_correlation -v
.venv/Scripts/python.exe examples/converter/run_pwm_volume_validation.py `
  --library build-peec-native/spikes_c_api.dll `
  --output-dir build/pwm-volume-correlation-<new-run>
```

All seven correlation tests passed with the actual native and CalculiX runtimes,
as part of a 62-test affected PWM/retained-solid/CalculiX regression run with no
skips. Architecture checks and 15 retained source/artifact hash checks passed.
The full Python discovery run completed successfully: 3,051 tests in 856.025 s,
22 skipped, zero failures/errors. This does not promote skipped capabilities or
constitute cross-platform, desktop packaging or human numerical qualification.
Both retained native and CalculiX runtime hashes matched the actual binaries.
The retained-board/package check also executed through the evidence CLI.
A missing optional runtime can skip its unit
tests, but such a skip is not evidence of correlation. The evidence CLI
requires real runtimes and fails rather than synthesizing successful output.

The final local evidence bundle is
`build/pwm-volume-correlation-20261010-v3/`. It contains original requests,
all coupled/window-refinement outputs, independent ODE history, complete
CalculiX histories, source/runtime hashes and artifact hashes. The earlier
directories predate retained window-refinement or real-mesh replay artifacts.

Two initial script attempts were not accepted evidence: a NumPy scalar was
rejected by strict schedule admission, and a 50 us CalculiX heat-transfer
card exceeded the external solver's numeric field width. The latter exposed
and led to a bounded deck-format correction with its own regression test.
The corrected actual histories above passed. Sandbox temporary-file denial
required ordinary local temporary-directory access for external solves.

All fixture geometry, equations, code and reference histories were independently
authored for SPIKE. No upstream implementation, example mesh, or external
test data was copied. The existing separately installed CalculiX executable
retains its own license; no external solver is redistributed by this evidence.
