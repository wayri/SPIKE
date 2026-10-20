<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0126: explicit 3-D land fields and independent finite face patches

Status: accepted for an experimental in-process reference; not release qualified.
Date: 2026-10-21.

## Problem

The planar RT0 contact model assigns one area distribution to a node. Distinct
barrel faces on the same land may require different distributions and conjugate
potentials. Gap ownership cannot supply the missing through-thickness land
current or heat, and clipping gap resistance requires a new coupled solve.

## Decision

Add an isolated, supplied Cartesian-prism mixed RT0 reference with prescribed
uniform finite rectangular current patches on any exterior side. Explicit
patch ID, side, rectangle and face IDs determine support; attachment labels
do not weld traces or impose equipotential conditions. Original 3-D face bases
and exact local Ohmic mass preserve cell KCL, shared face flux and Joule work.
Recover all traces, cell vector components and integrated heat; check the gauge
row after solution. Retained result admission recomputes support, local weak
law, conservation and terminal work without trusting pass flags or rerunning
the solve. See [method and reviewed foundations](../DC_LAND_TRANSITION.md).

Input admission/mapping, numerical solve and retained-result admission live in
separate small Python modules. This is a bounded reference implementation on
the existing NumPy/SciPy stack, not a performance kernel, registered desktop
engine or another implementation language. No new dependency or external
implementation is incorporated. The example CLI runs without an assistant.

## Consequences and limits

This resolves fields and exact integrated reconstructed heat in a declared
rectangular land, and keeps independent face patch potentials available for
future circuit coupling. It does not solve an attached circuit, impose an
equipotential metal electrode, import arbitrary annular/board geometry, or
establish a complete-board density distribution. External assembly must impose
the appropriate port current/voltage equations; identity labels alone never do.
Production and complete-board flags remain false. PI01-S02 stays in progress
until its source/contact, general geometry and original-board conditions pass.
Human numerical review and production/native performance work remain separate.
