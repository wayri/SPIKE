<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0108: executable SI/PI workflows and channel assignment recovery

Status: accepted, 18 October 2026.

## Context

Numerical kernels alone do not establish a runnable engineering workflow. The
SI workbench retained an invalid third-port receiver when changing the default
four-port channel to a two-port geometry/Touchstone channel. The explicit PDN
network worker lacked the ordinary saved-request CLI path available for SI.

## Decision

Add `pdn-network request.json` through the existing CLI-to-worker boundary,
preserving native model results, errors and output conventions. Add a small
frontend assignment helper: remap only a simple default through-path receiver
when the port topology changes, preserve endpoint model values and show a
notice. Retain custom assignments and block incompatible execution with
actionable messages. Backend admission remains authoritative.

Add a source-checkout readiness runner with real CLI subprocesses, independent
RC/RLC witnesses, explicit transient refinement and optional native copper
checks. Retain source/input/output hashes and actual logs in fresh folders.
No new physics, dependency, numerical tolerance waiver or qualification is added.

## Consequences

Users can run bounded supplied-model SI/PI and diagnose installation/model
admission failures. Passing synthetic checks does not qualify an arbitrary
board extractor, native visuals, physical accuracy or whole-suite parity.
The [runnable guide](../RUN_SI_PI_NOW.md) states supported paths and board inputs.
