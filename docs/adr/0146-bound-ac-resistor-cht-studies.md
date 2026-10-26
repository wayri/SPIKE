<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0146 Bound AC resistor and CHT study captures

Date: 25 October 2026

Status: Accepted for bounded source application integration; installed and
physical qualification remain separate.

## Context

The experimental AC/CHT runner exported a result without a saved study binding
its complete request. Generic study updates also invalidated unchanged setup
saves, while snapshot merging could restore removed physical input keys.

## Decision

Reuse SimulationStudy v1 with case type `em-resistor-cht`. A Python application
service, `prepare_em_resistor_cht_study`, owns structural target admission and
request/result digest binding. It calls no numerical solver. Existing AC/CHT
execution retains all mathematical and numerical admission responsibilities.

The existing EM co-simulation service routes preparation. The TypeScript adapter
stages a reviewed Python runner for an explicitly selected case or historical
capture. Activation never executes numerical code or publishes a saved capture
as a newly computed field result. Export/import uses existing study and project
persistence contracts rather than a separate project format.

Complete specialized studies are bounded to 3 MiB to retain round-trip access
through the existing 8 MiB worker envelope. Larger than 512 KiB editor drafts
use the small file-input runner instead. Source preparation, stored data and
physical qualification remain distinct.

Canonical setup comparison preserves unchanged results. Study settings/scenarios
are authoritative during snapshot replacement; deleting a physical input or
current result must not resurrect it from prior state. Immutable historical
captures retain their original setup and actual capture metadata.

## Consequences and verification

No equations, tolerances, solver claims or implementation language change.
Digest binding detects input mismatch; it is not source authentication or
independent result validation. Existing generic studies and unknown future
project fields retain their contracts. Installed workflow acceptance is open.

Regression coverage includes four physical edits, presentation edits, unchanged
saves, removal semantics, actual `.spike` write/read, real worker-backed runner
export/replay, ambiguous target rejection and asynchronous activation ordering.
See [saved AC/CHT study workflow](../EM_RESISTOR_CHT_STUDIES.md).
