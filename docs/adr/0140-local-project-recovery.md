# ADR 0140: Local portable project recovery

- Status: Accepted for development implementation
- Date: 2026-10-24

## Context

The old Settings autosave interval had no project-saving timer. Recovery must preserve current unsaved project state and embedded artifacts without overwriting primary files or changing project identity.

## Decision

A renderer timer submits the current portable snapshot through `write_project_backup`. A single scheduler excludes unchanged revisions and overlapping operations; it pauses for busy imports, loading, saving and assembly drafts. Settings enable/interval changes take effect on Apply. Old disabled autosave preferences migrate to disabled backups.

The native host injects a private application-data recovery root, rejects renderer path overrides and requires prior approval of any base package. Python owns portable writing, expected base manifest validation, metadata, OS locking and bounded retention. Recovery APIs use `spike/project-backup/v1` records and `spike/project-backups/v1` lists. Limits are ten per session, 512 MiB/package and 2 GiB total. Only validated prior backups are eligible for pruning; the active base is protected. Failed publication leaves the primary intact.

`open_project_backup` verifies digest and package before native approval. The normal project reader then verifies manifest identity and artifacts. Restoration keeps the recovery path for artifact reads but marks the project as a recovered copy. Save requires a new destination and retains the base for portable artifact copying. Recovery storage is not a normal editable project destination.

## Consequences and evidence

Unapplied drafts and Python editor buffers are outside the project snapshot. Browser preview has no durable native recovery. A timer is not an immediate save guarantee and large packages may exceed fixed storage limits. No cloud storage or dependency is introduced; no numerical behavior changes.

Regression evidence is in `app/scripts/test-project-backups.mjs`, `tests/python/test_project_backup.py` and native `project_backups::tests`. User behavior and limits are documented in [Project backups](../PROJECT_BACKUPS.md).
