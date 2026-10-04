<!-- SPDX-License-Identifier: Apache-2.0 -->
# Script model result viewport

Status: proposed for review, October 4, 2026.

## Decision

Keep script execution in the Python worker and admit bounded data views at both
worker and UI boundaries. App owns result activation; ScriptResultViewport owns
view selection/probing/plots; SpatialDataViewport owns and disposes its WebGL
resources. Closing results restores the normal board workspace.

Physical geometry and sample overlays require matching source/parameter identity,
run identity, explicit coordinates and units. Far-field display radius remains
presentation metadata. The separately licensed upstream example bridge uses
public EMerge APIs and preserves source provenance; it is not a numerical engine.

The editor retains SPIKE's debugging/context interfaces while adding explicit
external interpreters, floating controls and truthful indeterminate run state.
See [workflow and limits](../SPIKE_EM_UI_BACKPORT.md).
