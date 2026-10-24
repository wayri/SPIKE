# ADR 0143: Explicit experimental macOS sampled-memory policy

- Status: accepted for experimental package candidates, 24 October 2026
- Scope: trusted host supervision of the dedicated owned-circuit worker

## Context

Native macOS 15 Apple Silicon and Intel Python runtimes reserve virtual
address spaces larger than the circuit worker's 4 GiB absolute address-space
budget. Existing strict `RLIMIT_AS` admission fails before worker execution.
Changing the loader environment did not repair admission. The owner requested
macOS as an available target after the sampled-memory alternative was explained.

## Decision

Keep `strict_address_space` as the public supervisor API default. Add the
explicit Darwin-only `darwin_sampled_rss` policy. Package qualification selects
it explicitly; it is never a retry after strict admission failure. Windows
Job Object and Linux address-space enforcement remain unchanged.

The experimental policy samples the sum of process-group resident sets using
macOS `/bin/ps`. It retains session isolation, a zero core-dump limit, wall-time
and cancellation handling. Malformed, unavailable or failed observations abort
the owned group. Group termination retains the leader PID until the last signal.

Package manifests and qualification reports carry `release_supervision`,
including `hard_memory_cap: false`. DMGs include a readable policy receipt.
The dedicated worker capability lists this supervision method. A package
receipt describes its circuit probe, not a memory limit for the whole app.

## Limits and recovery

Sampling is not a hard allocation cap: memory can exceed budget between
observations and brief peaks may be missed. Shared resident pages can be counted
more than once. Descendants creating a new session escape process-group scope;
normal-exit orphan containment is not claimed. This is not a security sandbox.
An observation failure terminates instead of continuing without monitoring.
`SPIKE-BE-SPICE-E-0058` records sampled over-budget termination and
`SPIKE-BE-SPICE-E-0059` records observation failure. The strict admission failure
remains `SPIKE-BE-SPICE-E-0057`.

Hosts must explicitly select this policy. Unchanged third-party callers retain
the strict default and may still reject a macOS launch. The main in-process
SPIKES bridge and optional external solver paths have their own execution
contracts; they do not acquire this policy merely by running on macOS.

## Verification

Focused tests cover explicit selection, invalid inputs before execution,
resident-set parsing, observer failure and process-group cleanup. Native tests
must exercise both Mac architectures, including held allocations over budget,
then final installed payload admission and a real packaged circuit solve.
A built app or passing rejection test alone does not qualify a DMG.

## Primary interface references

Independently authored adapter; no external implementation copied.
Apple's [ps interface](https://raw.githubusercontent.com/apple-oss-distributions/adv_cmds/main/ps/ps.1)
defines process-group selection and resident sets in 1024-byte units.
Apple's [compat interface](https://raw.githubusercontent.com/apple-oss-distributions/Libc/main/gen/compat.5)
documents the explicit `COMMAND_MODE=unix2003` environment.
The earlier native AS admission evidence is retained in the
[Unix candidate record](../validation/UNIX_RELEASE_041_20261024.md).
