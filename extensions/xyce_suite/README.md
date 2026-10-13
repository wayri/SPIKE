# Xyce Circuit Suite

This original Apache-2.0 SPIKE extension connects to a separately installed serial
Xyce executable. It bundles no Xyce runtime, native plugin, model library or
upstream example. Solver/model licensing remains the user's responsibility.

Use the Xyce circuit setup application to select the native executable, paste a
native netlist, supply inert text libraries, prepare a private case, validate its
syntax, run it, and inspect its returned CSV waveforms and artifact identities.
Every netlist starts with a title line. Printed vectors require native
`.PRINT ... FORMAT=CSV`. No numerical output is inferred from the circuit.
Native syntax warnings/errors are preserved in structured diagnostics; the full
native log stays in the case directory. A missing runtime cannot produce a solve.

The SDK discovers `spike-extension.json`; its application contributions are
`xyce-circuit` (prepare or preflight), `xyce-validate`, `xyce-run`,
`xyce-inspect` and `xyce-cancel`. Parameters are:

- `operation`: preflight, prepare, validate, run, inspect or cancel.
- `netlist`: native text; `libraries`: at most 32 objects with `name` and `text`.
- `case_id`: opaque prepared ID, instead of new netlist/library text.
- `engine_options`: `executable`, `timeout_seconds` (1..300, default 120),
  `memory_limit_mib` (64..8192, default 2048).

Preflight accepts empty input and reports candidate availability. Discovery uses
an explicit executable exclusively, then `SPIKE_XYCE_EXECUTABLE`, then PATH.
Availability means an existing admitted file; it does not assert a successful
native runtime execution or validated model. Native executable SHA-256 is retained.
Inputs are independently hashed before every run; inspect checks saved waveform
digests. Input text and saved results are local review artifacts, not signed
security attestations.

Return `data` includes `engine`, `operation`, `status`, `solved`,
`case_id`, `runtime`, `diagnostics`, `waveforms` and `artifacts`.
Each waveform contains its filename, `columns: [{name, unit}]` and numeric
`rows`. Recognized time/frequency/voltage/current/phase units are s/Hz/V/A/deg/dB;
unrecognized expressions retain null units rather than guessing. Artifacts
contain names, byte counts and SHA-256. `model_status` is always experimental
and `production_qualified` is false. `validated_syntax` is only a native
syntax-check outcome. Only a zero native exit, no reported native errors and
nonempty finite admitted CSV waveforms give `solved: true`.

## Safety and recovery

Inputs stay under SPIKE's private state directory (`SPIKE_STATE_HOME`,
LOCALAPPDATA or the user's local state fallback), in `SPIKE/xyce-cases/<id>`.
No arbitrary directories, command arguments, scripts, MPI launcher, external
file references or native plugin loading are exposed. Supplied library names
are plain filenames ending in .lib/.inc/.cir; `.include` references must resolve
to supplied inert text. Recursive includes, external-code devices, filesystem
output qualifiers, control scripts and unsupported directives fail admission.
The conservative native subset includes AC/DC/transient/OP, models/subcircuits,
parameters, temperature, initial conditions and CSV print statements. It does not
translate ngspice/PSpice dialects. Some otherwise legitimate Xyce directives,
such as .OPTIONS, .MEASURE, .LIB section selection and file-driven sources, are
currently outside this admitted subset.

The existing process supervisor applies memory/wall-time limits. Windows uses
a Job Object with kill-on-close and one active process. Linux source Python uses
a fixed isolated exec guardian, sets the kernel parent-death SIGKILL with race
checks, then replaces itself with Xyce. Other platforms and frozen Linux workers
are rejected for execution until parent-death containment is implemented.
Desktop cancellation terminates the extension; the Job Object or Linux guardian
contains the solver. Direct API clients may also request case cancellation with
the marker contribution. Linux native containment has not been exercised on this
Windows checkout.

Limits include 2 MiB aggregate input, 8192 characters/line, eight print statements,
64 columns and 20000 rows/CSV, 4 MiB/CSV, 8 MiB/artifact, 32 MiB/case,
96 artifacts, 256 retained cases and 8 MiB transported results. Live size checks
request termination when artifact budgets are exceeded; polling is not an
OS filesystem quota and can briefly overshoot. Native executable admission is
bounded at 256 MiB and hashing is streamed. Repeated runs clear old native output
before launch. A case lock prevents concurrent execution. After interruption or a
stale lock, prepare a fresh case. If storage fills, review and remove old case
directories manually. Reduce printed vectors/time points for a result limit;
correct the native deck for dialect errors; select an installed executable for
runtime_unavailable. Timeout/cancellation/native failure never return solved
waveforms.

## Evidence and provenance

Official method/interface sources:

- [Xyce reference guide 7.7](https://xyce.sandia.gov/files/xyce/Xyce_Reference_Guide_7.7.pdf):
  native -syntax, -l and -o switches; CSV .PRINT output conventions.
- [Xyce users guide 7.7](https://xyce.sandia.gov/files/xyce/Xyce_Users_Guide_7.7.pdf):
  DC, AC and transient CSV output naming and voltage/current observables.
- [Xyce FAQ](https://xyce.sandia.gov/documentation-tutorials/frequently-asked-questions/):
  native dialect compatibility limits and observable restrictions.

Code, prose, netlists and CSV fixtures were independently authored without
examining or adapting upstream implementation or examples. The test divider uses
a 3 V source and 1200/600 ohm series resistors; Kirchhoff's laws independently
give 1 V at the midpoint and 1/600 A source magnitude. Mock process tests validate
admission and orchestration, not numerical physics. The optional actual-runtime
test checks the midpoint to 1e-8 V when Xyce exists on PATH. It is skipped on this
checkout because Xyce is absent. No native accuracy or release qualification is
claimed. Knowledgeable human numerical review remains required before release.

Run `python -B -m unittest discover -s tests/python -p test_xyce_extension.py -v`.
