<!-- SPDX-License-Identifier: Apache-2.0 -->
# Native AMI development host

Status: **experimental, trusted local development only**. Actual native
AMI_Init, sequential AMI_GetWave and AMI_Close calls execute in a disposable
child, never in the Python application process. This does not qualify a vendor
model, physical receiver, channel composition, PAM3 interface or protocol.
The non-executing [inventory](SI_AMI_INVENTORY.md) keeps its existing gates.

The [public candidate audit](validation/AMI_PUBLIC_ADMISSION_20261023.md) and
[owner-requested isolated-VM plan](SI_AMI_ISOLATED_VM_EVALUATION_PLAN.md) record
the current vendor-evaluation boundary. The plan is not approval to execute
an installer/model or accept its terms, and no external interoperability run
has yet been admitted.

## Trust and deployment boundary

Do not expose this function directly to generic worker JSON or imported
projects. Request booleans are acknowledgements from an already trusted local
caller, not authorization from an untrusted document. The caller must verify
the host installation, model origin, license and behavior before invocation.
Hashing identifies bytes; it establishes neither trust nor license rights.

Only Windows x64 is admitted. The Python adapter checks bounded PE64 headers,
machine and DLL/executable kind, hashes host/model bytes and inspects direct
imports without loading either. Only kernel32, msvcrt, ucrtbase and the Windows
API-set CRT imports are admitted; delay imports and other dependencies fail.
The model is staged from verified bytes in a fresh temporary directory; the
original model path is not loaded. Native loading restricts the default and
dependency search to System32. This is not complete dependency attestation:
runtime-generated loads, Windows platform libraries and host installation
integrity remain trust assumptions. The installed host is hashed then started;
concurrent replacement of that trusted installation is outside this boundary.

Existing `circuit_worker_supervisor.supervise_process` creates the child
suspended, assigns a Windows Job Object, then resumes it. A one-process limit
denies ordinary descendant creation. Memory limits, wall timeout, cancellation
and kill-on-job-close apply to that job. Failure to establish the job is fatal.
The C++ entry-point bridge is standalone; it must not be linked into the UI,
worker bindings or any long-lived application process.

**This is not a security sandbox.** Native code retains current-user access to
files, network, registry and other accessible processes. There is no disk quota
or total-I/O cap, and arbitrary native writes cannot be made memory-safe by the
AMI ABI. The job does not confine delegated service/WMI process creation or
other OS-service actions. Do not run untrusted binaries here. POSIX execution
is disabled: the existing process-group supervisor is insufficient to prevent
group escape, even though the native bridge has portable loader code.

## Python API and request

`python.spike_core.solvers.signal_integrity.receivers.si_ami_execution.execute_ami_native(request, *, host_path,
host_sha256, job_parent=None, cancelled=lambda: False)` is an explicit local
development API. `host_path` is an absolute ASCII path to the approved host;
`host_sha256` is its reviewed lowercase SHA-256. `job_parent` optionally chooses
an existing writable temporary-parent directory. It is trusted caller control,
not a request field. Temporary staged files are deleted after settlement.

The request requires exactly these fields:

| Field | Admission |
| --- | --- |
| `contract` | `spike/si-ami-execution-request/v1` |
| `platform` | `windows-x86_64` |
| `direction` | `tx` or `rx` |
| `model_file` | exactly absolute ASCII `path` and lowercase `sha256` |
| `dependencies` | empty list; non-system packages are unsupported |
| `trust` | `acknowledgement: "trusted-native-code-with-current-user-access"`, strict Boolean `license_reviewed: true`, `dependency_reviewed: true` |
| `parameter_text` | bounded original ASCII AMI parameter definition |
| `sample_interval_s`, `symbol_time_s` | positive finite seconds, interval no greater than symbol time |
| `impulse_response` | one through-channel column, 1..65,536 finite samples |
| `wave_blocks` | 0..64 ordered nonempty waveform blocks, at most 65,536 samples total |
| `timeout_s` | positive finite wall seconds, at most 300 |
| `memory_limit_mib` | integer 32..2,048 |

No aggressors, resolver, BCI, repeater or dual-clock-input flow is admitted.
Reserved declarations are limited to AMI_Version, Init_Returns_Impulse,
GetWave_Exists and false Resolve_Exists. Other reserved semantics fail closed.
Flat model-specific In/InOut parameters use their declared defaults. No
parameter sweep/override, symbolic UI conversion or nested input hierarchy is
implemented. Output strings undergo bounded ASCII, complete balanced-tree
syntax, scalar/value-list syntax and root-name checks before acceptance. They
otherwise remain opaque evidence: this is not an output-descriptor semantic
validator and does not interpret model-specific meanings.

A zero-block request is Init-only and requires Init_Returns_Impulse. Waveform
blocks require GetWave_Exists. An Init output declared invalid by
Init_Returns_Impulse false is returned as `impulse_response: null`, never as a
usable transformed channel. Caller-supplied waveform construction remains the
caller's responsibility: this API does not convolve Tx/channel/Rx chains or
interpret samples as a validated eye/BER result.

AMI Init receives samples of a continuous-time impulse response, not
dimensionless discrete FIR taps. For a voltage transfer gain, that impulse
response has units 1/s. Using a rectangular sample representation, unit area
requires `h[0] = 1/dt`, all other samples zero, so `dt * sum(h) = 1`.
A constant gain `G` returns area `G`; general numerical convolution includes
the `dt` factor: `y[n] = dt * sum(h[k] * x[n-k])`. This adapter transports the
supplied impulse unchanged into Init and performs no normalization/convolution.
The caller must supply the correct impulse normalization. Discrete PAM3 FIR
tap metadata belongs to a separate dimensionless contract and must not be
passed as a normalized continuous-time Init impulse without conversion.

## Lifecycle and bounded transport

The fresh process handles one session. Buffers and parameter text are owned by
the host; opaque state and returned character buffers remain model-owned.
Returned strings are copied before another model call and before Close.
Successful Init is followed by exactly one Close, including ordinary host-side
validation or GetWave failure. Init failure does not create a successful session;
the disposable process reclaims its resources. Fatal faults, timeout or killed
processes cannot promise a model Close callback. A failed Close fails the run.

No partial result is installed. The private little-endian binary request and
result framing has version magic, explicit counts and fixed binary64 samples.
Requests are fully read/validated before library load. Parameters and each
returned string are at most 16,384 bytes. Native host output is bounded by these
sample/string counts; Python accepts at most 4 MiB of binary output and 4 MiB of
JSON result. The native model itself is at most 32 MiB. These are local policy
limits, not specification maxima or protection against malicious file writes.

Rx clock arrays allocate `wave_size + 1` doubles, poisoned before every call.
This subset permits at most one clock per input sample; since `dt <= UI`, this
capacity is at least `1 + ceil(wave_size * dt / UI)`. A model must provide a -1
sentinel, nonnegative finite clocks and strict monotonicity within and across
blocks. Tx receives a null clock pointer. There is no recovered-clock quality,
lock, acquisition, timing-mask or physical clock validation.

Success returns `spike/si-ami-execution-result/v1`, status `completed`,
model_status `experimental`, production_qualified false, sandboxed false,
opaque Init/GetWave parameter/message evidence, impulse and block outputs,
and host/model/parameter/request hashes with sample timing, direction and OS
supervision provenance. `qualification: synthetic_abi_only` labels the host's
test evidence, not the supplied model's physical qualification. Failures raise
`SiAmiExecutionError`; OS admission/IO failures may raise the underlying OS
exception. Retain the original model and input; do not remove unsupported
declarations to bypass a failure.

## Source review and original test oracles

Reviewed 23 October 2026: official [IBIS 8.0](https://ibis.org/ver8.0/ver8_0.pdf),
ratified 5 December 2025, section 10.2.3, pages 222-234: signatures, ownership,
return codes and clock rules; section 10.3.6 input-parameter handling is limited
to the inventory/default subset above. AMI_Close returns `long`, not `void`.
No specification example implementation or external model source was used.

Microsoft's [PE format](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format),
[LoadLibraryExW](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-loadlibraryexw)
and [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
documentation was reviewed for PE headers/import tables, System32 search flags,
job association and its non-sandbox limits. The implementation and fixtures
were independently authored; no upstream source, test model or dataset is
bundled. Host transport changes no governing physical law.

The synthetic numerical oracles are deliberately elementary exact recurrences:
identity `y[n]=x[n]`; FIR `y[n]=3*x[n]/4+x[n-1]/4`; and stateful filter
`y[n]=(x[n]+y[n-1])/2`, all starting from zero history. Substituting a unit
impulse yields `[3/4,1/4,0,...]` and `[1/2,1/4,1/8,...]` respectively.
The Python oracle iterates the entire sequence independently, then compares
one-block and split-block native calls. Binary-exact coefficients/fixture
values support exact equality; clock seconds use a 1e-26 absolute tolerance.
These authored discrete test functions establish ABI state continuity only,
not independently measured device physics or qualification of an IIR method.
Separately, the continuous-time normalization test supplies impulses of height
`1/dt` at 1, 2 and 5 ps intervals. Independently authored identity, unity-sum
FIR and constant-gain-two native fixtures must preserve areas 1, 1 and 2,
respectively, within an absolute 5e-15 tolerance. The gain fixture must also
double the waveform. This derives directly from the continuous-time input
interpretation in IBIS 8.0 section 10.2.3 (page 225) and the definition of a
unit-area impulse; it verifies units/transport without claiming measured
device behavior or general analog discretization accuracy.

## Reproduction and limitations

From a Windows x64 source checkout with MSVC and CMake:

```powershell
cmake -S tests/fixtures/ami_native -B build-ami-host -G "Visual Studio 18 2026" -A x64
cmake --build build-ami-host --config Release -- /m:1 /nr:false
.venv/Scripts/python.exe -m unittest tests.python.test_si_ami_execution -v
```

Set `SPIKE_AMI_TEST_BIN` to an alternate directory containing the host and all
fixture DLLs. The fixtures use static MSVC runtime linkage. If native artifacts
are absent or Windows is unavailable, executable cases explicitly skip; parser
tests alone do not establish execution success. The module does not download,
install or compile a supplied model automatically.

The executed Windows/MSVC checks cover identity with three input levels,
FIR and state continuity, Init-only/Tx/Rx, invalid declared Init impulse,
failure returns at all three entry points, crash containment, timeout and
cancellation, invalid clocks, missing exports, wrong root/nonfinite output,
malformed Init/GetWave output trees, continuous-time impulse area/gain,
digest/platform/dependency/trust rejection and maximum sample count.
The child-process denial fixture tests the Job Object's one-process limit.
No vendor-model or external-tool numerical comparison is available. External
candidate binaries inspected by the integration owner were not admitted;
that is an external evidence gap, not a host qualification success.

Before broader enablement: independent security/lifecycle review, approved
binary/license/dependency packaging, supported-platform qualification, external
vendor/reference comparisons and knowledgeable human release review remain
required. Untrusted-code sandboxing needs a separate design and implementation.
