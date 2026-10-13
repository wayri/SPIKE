<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKES native controller execution speed

## Scope

Studio's trusted C/C++ sampled controller keeps the existing
`spikes/generic-controller/v1` configuration unchanged. The default execution
mode still starts a fresh compiled process for every controller tick:

```python
controller = Controller(config, trusted=True)
```

This default preserves the original behavior: explicit `state_N` values pass
between ticks, while C/C++ global and function-static variables reset on every
tick.

Callers that accept different native-state lifetime semantics may opt in to one
long-lived compiled worker:

```python
controller = Controller(
    config,
    trusted=True,
    execution_mode='persistent_process',
)
```

`execution_mode` is a constructor option, not a saved controller-config field.
Existing project files, library records, and callers therefore retain the
fresh-process contract.

## Persistent-process behavior

The persistent wrapper reads one bounded JSON request line at a time and emits
one response line. Python still owns orchestration, request IDs, explicit state,
pin conversion, output envelopes, and error handling. `control_step` remains
compiled C/C++; this mode removes native process creation from warm ticks, but
it is still Python IPC and is not a hard-real-time execution path.

In persistent mode:

- explicit `state_N` values remain authoritative and cross the JSON boundary;
- C/C++ global and function-static variables also survive warm ticks;
- `reset()` terminates the worker, clears explicit state and tick count, and
  therefore resets native static storage before the next tick;
- `close()` terminates the worker and later `step()` calls fail;
- a timeout, crash, oversized/non-line output, malformed JSON, duplicate key,
  wrong request ID, or wrong response schema rejects that tick and terminates
  the worker to avoid protocol desynchronization;
- stdout is limited to one SDK-bounded response line at a time, the reader
  queue is bounded, stderr capture is bounded, and each request uses the SDK
  timeout across request write, flush and response. A non-reading callback is
  terminated on timeout; a surviving I/O thread prevents further worker starts.

The response is admitted through the same compiled-block SDK response type and
contract/schema checks used by fresh execution. Executable identity is checked
before a persistent worker starts. No failed response advances explicit state
or the tick counter.

## Trust and isolation boundary

Both modes require `trusted=True`. A native worker is process-isolated from the
Python interpreter, but it is not a hostile-code sandbox. Approved controller
code can access resources available to its operating-system process. Persistent
mode increases the lifetime of that process and of its native globals; use it
only for reviewed code whose state lifetime is acceptable.

## Reproducible 50-tick comparison

Run the focused actual-compiler test from the repository root:

```powershell
python -m unittest standalone.spikes_project.tests.python.test_controller_persistent.PersistentControllerTests.test_50_tick_actual_process_comparison -v
```

The test compiles the same controller configuration for both modes, excludes
compilation time, executes 50 ticks with identical inputs, and asserts identical
outputs and final explicit state. The fresh sample contains 50 cold process
starts and no warm ticks. The persistent sample contains one cold start and 49
warm ticks. Timing is reported, but there is deliberately no absolute speed or
ratio assertion because host load and process-start cost vary.

One Windows development run on 2026-10-13 with MSVC 19.51 reported:

| Mode | Cold ticks | Warm ticks | Elapsed | Throughput |
| --- | ---: | ---: | ---: | ---: |
| `fresh_process` | 50 | 0 | 1.031294 s | 48.5 ticks/s |
| `persistent_process` | 1 | 49 | 0.052579 s | 951.0 ticks/s |

These numbers are one reproducible comparison, not a performance guarantee.
Use the command above on the target machine for current evidence.

## Verification coverage

`test_controller_persistent.py` uses actual compiled C and C++ code to cover
input/output transport, explicit state, default per-tick native-static reset,
opted-in static persistence, reset, malformed output, timeout, native crash,
close, and the 50-tick comparison. Existing controller tests continue to cover
the default constructor path and native closed-loop use.
