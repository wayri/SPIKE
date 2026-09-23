# SPIKE Error Handling

## Purpose

SPIKE uses one diagnostic contract across the desktop frontend, local workers,
solver plugins, external-engine adapters, CLI, reports, and future remote
workers. The contract is intentionally independent of transport and UI state.

The foundation consists of:

- `python/spike_core/errors.py`: parser, immutable catalog, safe envelope
  builders, and `SpikeError`.
- `schemas/error-envelope-v1.schema.json`: serialized contract.
- `docs/ERROR_CODE_CATALOG.md`: issued-code reference.
- `TROUBLESHOOTING.md`: symptom-first operator recovery sequences.

This foundation does not silently convert existing arbitrary messages. A
subsystem must choose a registered code at the point where it understands the
failure. Unknown exceptions are converted only at a process boundary using an
explicit registered fallback.

## Code Format

```text
SPIKE-{ORIGIN}-{DOMAIN}-{CLASSIFICATION}-{SEQUENCE}
```

Example:

```text
SPIKE-BE-SOLVER-E-0002
```

The fields are:

| Field | Meaning |
|---|---|
| `SPIKE` | Fixed product namespace. |
| `ORIGIN` | Tier that first detected the event: `FE` or `BE`. |
| `DOMAIN` | Stable subsystem owner such as `PROJECT`, `SPICE`, or `MESH`. |
| `CLASSIFICATION` | Operational class: `I`, `W`, `P`, `E`, `C`, or `S`. |
| `SEQUENCE` | Four decimal digits scoped to origin, domain, and class. |

Parsing is strict. Codes are ASCII, uppercase, untrimmed, and exactly four
digits at the end. No aliasing or case folding is performed. A code may pass
the grammar parser but still be rejected when it is absent from the immutable
catalog. This separates forward-compatible syntax inspection from issuance.

## Origin Tiers

| Origin | Owner | Typical detection point |
|---|---|---|
| `FE` | Frontend | UI state, viewport, user interaction, frontend project handling, or worker transport. |
| `BE` | Backend | Importers, meshers, numerical solvers, worker dispatch, report generation, and external processes. |

The origin records where an event was first detected, not where it is
displayed. A backend error rendered by React remains `BE`. Frontend wrapping
must preserve the backend code and may add a frontend code only as a separate
causal envelope.

## Classifications

| Token | Name | Meaning |
|---|---|---|
| `I` | Information | Progress or state information; no fault is asserted. |
| `W` | Warning | Work completed or can continue, but validity or completeness needs review. |
| `P` | Performance | A time, memory, throughput, or rendering budget was reached or degraded. |
| `E` | Error | The requested operation failed, normally with a bounded recovery path. |
| `C` | Critical | State integrity is uncertain or the owning process cannot safely continue. |
| `S` | Security | Trust, integrity, credential, sandbox, or prohibited-content policy failed. |

Classification is not solver validity. `Validated`, `Approximate`,
`Unsupported`, and `Failed to converge` remain numerical/model statuses. For
example, nonconvergence is an `E` diagnostic whose result status is `Failed to
converge`; a warning must never promote it to a valid result.

## Domains

The v1 grammar reserves these ownership domains:

`APP`, `PROJECT`, `PACKAGE`, `IMPORT`, `VIEW`, `PI`, `SI`, `THERMAL`, `EMI`,
`SPICE`, `SOLVER`, `MESH`, `PROBE`, `REPORT`, `EXT`, `IPC`, and `SECURITY`.

Choose the domain that owns the remedy. For example, a malformed worker
request is `IPC`; a numerically singular solve is `SOLVER`; an invalid cell is
`MESH`; failure to launch openEMS is `EXT`.

Adding a domain is a schema change and requires coordinated parser, schema,
catalog, test, and documentation updates.

## Envelope Contract

Every serialized envelope has contract `spike/error/v1` and contains:

| Field | Required | Purpose |
|---|---|---|
| `contract` | yes | Exact schema discriminator. |
| `code` | yes | Registered canonical code. |
| `origin` | yes | `FE` or `BE`, derived from `code`. |
| `domain` | yes | Domain derived from `code`. |
| `classification` | yes | Class derived from `code`. |
| `sequence` | yes | Integer form of the final four digits. |
| `title` | yes | Short immutable catalog title. |
| `message` | yes | Bounded event-specific or catalog-default message. |
| `detail` | no | Bounded user-safe detail. |
| `recoverable` | yes | Whether a supported recovery path exists. |
| `retryable` | yes | Whether retry can be appropriate after the remedy. |
| `user_action` | yes | Immutable catalog guidance. |
| `docs_anchor` | yes | Native-help target. |
| `timestamp_utc` | yes | RFC 3339 UTC timestamp ending in `Z`. |
| `operation_id` | no | Correlation ID for one bounded operation. |
| `cause_code` | no | Registered canonical code for the direct cause. |
| `context` | yes | Bounded, redacted, JSON-safe diagnostic values. |

The helper derives structural fields from the parsed code. Callers cannot
provide contradictory origin, domain, classification, title, or recovery
metadata.

## Safe Context Policy

`redact_context()` creates a copy and never serializes a traceback or an
arbitrary object representation. It applies these controls:

- Keys associated with passwords, tokens, API keys, authorization, cookies,
  credentials, private keys, license keys, secrets, or sessions are replaced
  with `[REDACTED]` at every nesting level.
- Bearer/basic credentials and URLs containing user information are redacted
  when they appear as string values.
- Binary values are redacted.
- Strings, nesting depth, mapping size, and sequence size are bounded.
- Cycles are replaced with `[CYCLE]`.
- NaN and infinity become JSON `null`.
- Unknown objects are represented only by their type name.

Context must not contain board source text, model source text, netlists,
environment dumps, stack traces, personal paths unless necessary, or design
geometry. Use stable IDs, counts, units, hashes, and bounded parameter values.
Redaction is a last line of defense, not permission to collect secrets.

## Python Usage

Raise a known operational error where the subsystem understands the remedy:

```python
from python.spike_core.errors import SpikeError

raise SpikeError(
    "SPIKE-BE-SOLVER-E-0002",
    "DC solve did not converge after 500 iterations.",
    context={
        "analysis_id": "dc-main",
        "iterations": 500,
        "residual": 2.7e-5,
    },
)
```

At the owning process boundary, serialize it:

```python
from python.spike_core.errors import envelope_from_exception

try:
    run_operation()
except Exception as error:
    response = {
        "ok": False,
        "error": envelope_from_exception(error, operation_id="solve:42"),
    }
```

Do not catch and reclassify an error at every layer. Preserve `SpikeError`
until the process or transport boundary. Wrap only when the higher-level
failure has a distinct remedy, and retain the direct registered code in
`cause_code`.

## Issuing a New Code

1. Confirm that no existing code has the same remedy and semantics.
2. Select the detecting origin, remedy-owning domain, and classification.
3. Allocate the next unused sequence in that origin/domain/class group.
4. Add frozen metadata to `ERROR_CATALOG` in `errors.py`.
5. Add the entry to `ERROR_CODE_CATALOG.md`.
6. Add focused tests for detection, redaction, and recovery metadata.
7. If a new domain is needed, update the parser and JSON schema in the same
   change.

Never recycle a published code. If semantics change materially, retire the old
code in documentation and issue a new sequence.

## Logging and UI Rules

- Logs and the UI display the same canonical code.
- The UI uses `title`, `message`, `user_action`, and `docs_anchor`; it must not
  infer success from a warning or suppress critical/security events.
- Console details may include the safe `context`, but no traceback is sent to
  ordinary users. Internal crash artifacts are stored separately with explicit
  consent and access controls.
- Reports include codes affecting numerical validity and reproducibility.
- Telemetry, if enabled in a future release, sends code and bounded counters,
  never raw context by default.
- Performance diagnostics remain distinct from numerical errors so users can
  tune resource policies without confusing them with solver validity.

## Test Requirements

The focused suite must verify:

- all origins and classifications round-trip through the strict parser;
- malformed, normalized, or unknown-domain strings are rejected;
- catalog mappings and metadata are immutable;
- unregistered codes cannot be emitted;
- code fields and envelope fields cannot disagree;
- context is bounded, recursive, JSON-safe, and redacted;
- generic exceptions do not expose a traceback or arbitrary representation;
- schema grammar and runtime grammar remain synchronized.

Run:

```powershell
& 'C:\Users\example\AppData\Local\Python\bin\python.exe' -m unittest tests.python.test_errors -v
```
