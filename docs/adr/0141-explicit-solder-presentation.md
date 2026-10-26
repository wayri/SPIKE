# ADR 0141: Explicit solder connection presentation

- Status: Accepted for development implementation
- Date: 2026-10-24

## Context

Electrical/thermal component bonds already identify pins and pads and carry explicit contact properties. Users need authored solder shapes in the main 3D viewport without guessing engineering values from cosmetic geometry.

## Decision

Optional `solderVisual` and `boardInstanceId` fields extend the retained desktop bond record. Dimensions are authored millimetres; style, visibility and opacity are presentation fields. Existing snapshots, undo and portable project persistence retain them. Unchanged `bondsForSolver` omits those fields, preserving the current electrical/thermal contract.

Unique pad ownership, reference, number, net and exposed surface must match before rendering. Multiboard display requires occurrence identity; no repeated reference or nearest-position association is guessed. Unsupported geometry is omitted with diagnostic review. Drilled profiles preserve the hole. Parameter admission bounds dimensions and the display is capped at 2,000 surfaces, instanced by geometry and opacity.

BoardViewport applies existing world/occurrence placement, layer visibility, display opacity and clipping. Solder meshes do not intercept pad selection and are not added to solver-domain or manufacturing geometry. The existing scene disposer releases owned meshes, instance buffers, materials and geometry.

## Consequences and verification

These simplified authored profiles do not establish solder quality, reflow geometry, fatigue, strength, material validity or a validated 3D electrical/thermal solder model. Standalone unowned terminals require a separate identity workflow. Existing bond analysis values remain explicit inputs.

Behavioral evidence: `app/scripts/test-solder-joints.mjs`, `test-solder-joint-editor.mjs` and `tests/python/test_solder_project_persistence.py`. See [workflow and limits](../SOLDER_CONNECTIONS.md).
