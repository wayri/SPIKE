<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0045: Explicit PI engineering comparison tools

Status: experimental implementation; numerical human review required before release.
Date: 2026-10-09.

## Decision

Keep three independently authored Python kernels separate from worker transport
and React presentation. Expose bounded, read-only worker and MCP operations for
steady converter loss balance, resistance routes on admitted copper, and
single-capacitor comparisons on supplied passive sampled impedance networks.
Use existing SpiDeR/hybrid mesh for copper route evidence. Do not infer a
switching converter netlist or a board impedance matrix from component names.

Preserve occurrence and component identities. Match retained numerical results
to their complete original request; component names alone cannot establish
input identity. Present explicit approximate status and returned quantities.

## Evidence and consequences

Independent analytical converter equations, periodic RL/RK4 refinement, direct
complex nodal network solutions, and analytical copper resistance fixtures
verify these bounded calculations. Worker/MCP tests execute actual kernels.
Public request schemas cover the converter and capacitor inputs. The return
assistant requires exact admitted copper geometry and pad ownership.

Switching control, transient SPICE/thermal feedback, geometry-derived capacitor
placement, continuous spatial optimization and hardware qualification remain
separate work. See [workflow and limits](../PI_ENGINEERING_TOOLS.md).
