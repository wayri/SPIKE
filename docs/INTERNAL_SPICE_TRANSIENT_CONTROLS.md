<!-- SPDX-License-Identifier: Apache-2.0 -->

# Internal SPICE transient controls

## Scope

The bounded internal deck route accepts:

```text
.tran TSTEP TSTOP [TSTART [TMAX]] [UIC]
```

`TSTEP` is the returned-output interval, `TSTOP` is the final analysis time,
`TSTART` is the first retained output time, and `TMAX` bounds the fixed internal
integration step. `UIC` remains the existing request to skip operating-point
initialization in the owned C++ route. This increment is an internal
compatibility slice and does not establish general ngspice transient parity.

The parameter meanings and the requirement that analysis begins at zero even
when earlier samples are not retained come from the
[ngspice user manual, transient-analysis section](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf).
The implementation, tests, grid construction, and prose were independently
authored; no ngspice implementation source or test data was consulted or
adapted.

## Output and integration behavior

SPIKES separates the public output grid from the integration grid:

- Integration begins at zero and continues through `TSTOP`. `TSTART` filters
  returned samples after integration; it never initializes a new solve.
- The output grid begins at `TSTART`, advances by `TSTEP`, and includes
  `TSTOP` as a final sample when the interval does not land there.
- With explicit `TMAX`, the fixed integration step is at most
  `min(TSTEP, TMAX)`. It is reduced when needed so the integration reaches
  `TSTOP` exactly. Returned quantities are linearly sampled from that grid.
- Without `TMAX`, the owned native runner keeps its prior `TSTEP` integration
  request, including a partial final step. The Python reference runner keeps
  the prior step when it lands on `TSTOP`; otherwise it chooses a bounded
  fixed step that reaches the required final sample. This intentionally avoids
  adopting ngspice's adaptive default-step policy.
- Both integration and full-capture output grids are limited to 1,000,000
  points. Non-finite ratios and excess point counts fail before allocating the
  corresponding grid.

The parsed analysis contract records `time_step_s` as `TSTEP`, plus
`start_time_s` and optional `maximum_time_step_s`. The Python MNA request
records its effective fixed step separately from `output_time_step_s` and
`output_start_time_s`. Results report the effective step, output point count,
integration point count, integration origin, requested maximum step, output
sampling policy, and final-stop inclusion.

## Source sampling

The Python reference MNA route evaluates analytic `SIN`, `EXP`, and `SFFM`
sources at every integration time. The owned C++ ABI supports these forms
through PWL lowering. That lowering is now sampled on the integration grid,
including when explicit `TMAX` makes it finer than `TSTEP`; otherwise a delayed
or higher-frequency source could be lost before the coarse output samples.
Provenance identifies the integration-grid lowering and whether exact samples
refer to the legacy requested grid or the finer integration grid.

## Validation and limits

`tests/python/test_spikes_transient_controls.py` checks contract round trips,
old-contract defaults, ordered-bound rejection, finite point budgets,
zero-origin RC evolution before `TSTART`, explicit `TMAX` enforcement, delayed
source resolution, final-stop output, two-argument regression behavior, and an
actual loaded owned C ABI library. It also runs the bundled Windows ngspice 46
executable on a delayed-source RC case and checks the retained start window,
final stop, and bounded agreement of the first retained voltage. The existing
transient, SIN, EXP, and SFFM suites cover the affected routes and source
equations.

The internal engines still use fixed-step integration. Linear interpolation of
returned values is an output policy, not an additional integration solve.
Adaptive local-error control and ngspice breakpoint scheduling are outside this
slice. The Python reference adapter does not independently qualify complete
ngspice `UIC` behavior; the owned C++ runner maps `UIC` to its existing
operating-point initialization switch. The RC comparison is evidence for this
bounded control case, not a whole-engine parity result. Environments without
the bundled Windows executable explicitly skip that cross-engine test.
