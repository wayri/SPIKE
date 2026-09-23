# Native OSDI callback boundary qualification

## Qualified capability

SPIKES can execute a digest-bound OpenVAF OSDI 0.3 model without ngspice in the
callback path. Trusted modules can be registered directly into the C++ DC MNA
kernel; hostile-marked requests use the Windows AppContainer worker route.

The release-qualified subset is:

- exact OSDI ABI 0.3;
- descriptor and allocation bounds;
- `setup_model` and `setup_instance`;
- DC `eval` with operating-point flags;
- resistive residual loading;
- resistive Jacobian loading;
- direct native C++ residual/Jacobian stamping;
- finite-value and structural result checks; and
- digest binding of Python, worker, manifest, compiler, source, and artifact.

The CC0 1 kOhm fixture was compiled by the installed OpenVAF 23.5.0 toolchain.
At terminal voltages `[1 V, 0 V]` it returns residual `[1 mA, -1 mA]` and the
matrix `[[1 mS, -1 mS], [-1 mS, 1 mS]]`, all within `1e-12` absolute error.

Evidence:

- `artifacts/spikes-osdi-native-qualification-wave6-2026-08-31.json`
- `tests/python/test_spikes_osdi_runtime.py`
- `scripts/run_spikes_osdi_native_qualification.py`
- `tests/test_spikes_dc.cpp`

## Security contract

The direct C++ route is for trusted, digest-reviewed native models only. The
Windows hostile route stages the exact worker/model, launches a zero-capability
AppContainer, grants its SID access only to staged entries, and applies a Job
Object one-process/512 MiB/kill-on-close policy. Time, request, result,
descriptor, allocation, and numeric values are bounded. A real model callback
passes while independent forbidden-file and TCP-connect probes fail with
`ERROR_ACCESS_DENIED` and `WSAEACCES`. Evidence is retained in
`artifacts/spikes-appcontainer-osdi-qualification-2026-08-31.json`.

## Remaining release blockers

- Qualify transient/reactive, AC, noise, limiting, parameter-access, state,
  event, and node-collapse callbacks.
- Add OSDI 0.4 descriptor-size traversal and qualify the extended ABI.
- Extend equivalent hostile-code isolation to non-Windows hosts and to compiled
  C/C++/HDL control blocks.

The Windows hostile-code claim is limited to the qualified staged OSDI 0.3 DC
worker. General hostile compiled blocks and multi-tenant execution remain
prohibited.
