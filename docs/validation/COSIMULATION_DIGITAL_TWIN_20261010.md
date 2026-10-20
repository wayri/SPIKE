# Co-simulation and recorded digital twin evidence, 2026-10-10

Scope: experimental scalar orchestration and offline residual comparison.
This evidence does not qualify physical solvers, live twins, FMI or hardware.
See [workflow and staged implementation plan](../COSIMULATION_DIGITAL_TWIN.md).

## Final focused checks

Using `C:/Users/yawar/AppData/Local/Programs/Python/Python311/python.exe`:

```powershell
python -m unittest tests.python.test_cosimulation tests.python.test_digital_twin tests.python.test_service_simulation_handlers -v
```

26 tests passed: 10 co-simulation, 12 digital twin and 4 existing simulation
handler tests. The raw `cosimulation-feature-validation.log` is an unbundled
local record; see [the release evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).
Coverage includes simultaneous delayed feedback, participant order independence,
exact unit/port admission, adapter configuration immutability, accepted tick
atomicity, cancellation/timeout, finite results, input/frame/trace bounds,
stale model rejection, exact timestamp coverage, independently calculated
residual/RMSE values, schema conformance, worker dispatch and CLI exit codes.

The checked-in synthetic demo runs successfully. Predicted load values are
0,2,4,6 V; synthetic measurement residuals are 0,0.1,-0.3,0 V. Maximum error
is 0.3 V, RMSE is sqrt(0.025) V, and one sample exceeds 0.25 V. These are
original synthetic fixtures, not hardware measurements. All accepted values
contribute to metrics even when retained traces are truncated.

Also passed:

- `python scripts/check_architecture.py` and `npm.cmd run check:architecture`.
- `npm.cmd exec tsc -- --noEmit`.
- `npm.cmd run test:parser`.
- `node scripts/test-python-templates.mjs`: 55 templates, 19 categories,
  13 guarded execution runners; the existing workspace starter is preserved.
- `cargo test`: 44 passed, 1 live OS counter test ignored. Normal filesystem
  access was required after the sandboxed Tauri build reported access denied.
- Diff whitespace checks for touched tracked files.

## Full-suite limits

`python -m unittest discover -s tests/python -v` completed with 3,105 tests,
17 errors and 22 skips in the Python 3.11 environment. It is not a green
full-suite result. The raw `cosimulation-python-validation-unrestricted.log` is
an unbundled local record.
The run began during editing and imported the earlier co-simulation module;
its schema test subsequently saw the newer schema requiring input/output unit
provenance. The final focused rerun passes that test with matching current code
and schema. The entire long suite was not rerun after the final edits.

The other errors are outside this feature: missing `pyarrow` in Arrow geometry
and project-package tests, a pre-existing Python 3.11 f-string parse error in
`examples/high_speed_si/render_reports.py`, and SPIKES native DLL load failures
with WinError 193 in EXP/SFFM tests. Those implementations and dependencies
were not changed to mask validation failures. A fully provisioned compatible
runtime and native DLL, followed by a clean full-suite run, remain necessary
for release validation. Knowledgeable human review of numerical changes before
release remains required by the project contribution policy.
