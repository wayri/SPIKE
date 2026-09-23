# SPIKES compiled control-block boundary

Status: bounded execution foundation. This is not Verilog-A, OSDI, Verilog, or
VHDL compiler support, and it is not a sandbox for hostile native code.

`python/spikes/compiled_blocks.py` defines the `json-subprocess-v1` protocol for
an explicitly reviewed local control block. The boundary is intentionally
fail-closed:

- a canonical manifest binds the executable SHA-256, fixed argument vector,
  language/runtime metadata, ports, state variables, and capabilities;
- an independent approval binds the exact manifest and executable digests plus
  review evidence;
- execution re-hashes the selected executable and uses an argument vector with
  `shell=False`;
- requests and responses use versioned, strict JSON objects containing finite
  numeric values only; duplicate keys, non-finite values, extra fields, wrong
  ports, and wrong state are rejected;
- input, combined stdout/stderr, argument, port, state, and wall-time limits are
  enforced; the child receives a fresh working directory and minimal
  environment;
- runtime errors expose stable codes instead of treating partial output as a
  simulation result.

The implementation-language field remains provenance metadata. The separate
`python/spikes/hdl_frontend.py` boundary can discover and invoke installed
OpenVAF, Icarus, Verilator, or GHDL tools using content-addressed plans, and can
validate an OSDI package manifest. It does not load OSDI into native MNA or turn
this subprocess protocol into an analog model callback ABI. Production support
still requires solver callbacks and Jacobian contracts, deterministic event
semantics, platform qualification, signatures/revocation, and an OS sandbox or
stronger isolation for untrusted or multi-tenant execution. The current process
boundary is only for trusted, digest-reviewed local executables. See
`SPIKES_HDL_FRONTEND.md`.

The unit suite in `tests/python/test_spikes_compiled_blocks.py` exercises the
approved success path, content tampering, approval denial, executable mismatch,
schema and finite-value rejection, timeout, and combined-output limits.
