<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0132: Read-only Assistant work folders and reviewed Python drafts

Date: 23 October 2026. Status: implemented in source.

## Problem

The integrated chat could explain files and draft code but had no direct path to
inspect a local input folder, calculate simple CSV statistics or stage that draft
in the existing Python editor. User requests were confused with capabilities
provided only by a separate coding agent. The owner requested a task harness and
selected staging generated scripts in the Python workspace for review and Run.

## Decision

The owning main workspace holds a transient user-selected root. A native picker
sets it; the model only supplies confined relative names. The detached Assistant
cannot invoke `assistant_work_files` through its raw worker channel or inject a
root. Its typed command goes to the owner, which injects that root and delegates
bounded read-only file/CSV operations to Python. Project/folder revision changes
discard stale evidence. The root is not persisted in projects or chat records.

`assistantTaskHarness.ts` owns this adapter; `assistant_harness.py` owns filesystem
admission, bounded extraction, hashes and descriptive statistics. There is no new
parser/numerical domain in the Rust host or TypeScript. CSV statistics use ordinary
finite binary64 descriptive arithmetic with supplied units and no solver claim.

`spike_python_draft` is an edit-class tool requiring the existing source-visible
review. The exact reviewed string is hashed and passed as a new unsaved editor
draft, retaining the trusted work folder separately as working-directory metadata.
It never calls `run_python_script`, writes files, executes shell commands or
applies CAD changes. Existing user Save/Run controls retain those responsibilities.
Existing event-based context-script admission does not accept a work-folder field.

The model receives known-tool validation errors as tool evidence and can repair
arguments. Identical failed calls are not dispatched again within the same turn.
Unsafe argument keys, action reviews and revision checks remain enforced. The
provider tool-descriptor cap increases from 32 to 40 for the expanded catalog;
round/call/history/request bounds remain independent and unchanged.

## Consequences and validation

This removes repeated file-copy and code-copy work while preserving explicit
execution. It does not add general filesystem agents, arbitrary code execution,
durable task memory, PDF ingestion, automatic native CAD import or new solvers.
Runtime dependencies and provider/model competence still matter. No persistent
journal is written, so this introduces no concurrent project-record writer.

Acceptance checks and known platform limits are documented in the
[task harness guide](../ASSISTANT_TASK_HARNESS.md). Regression fixtures exercise
safe-folder injection, drift, rejection, bounded I/O, known-answer statistics and
unsaved draft handoff. Live-provider fixture testing and native desktop acceptance
are distinct evidence classes. No claim of native acceptance follows from a
mocked picker/editor callback.

The native import picker is asynchronous: retaining the same approved-path
registration and filters while waiting for the OS dialog no longer blocks the
Tauri UI event loop. Folder selection has a dedicated 30-minute bridge timeout;
ordinary requests retain 150 seconds. The folder command remains UI-only,
argument-free and revision checked.
