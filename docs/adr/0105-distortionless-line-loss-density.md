<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0105: distortionless line attenuation and local loss density

Status: accepted for experimental implementation, 18 October 2026.

## Context

The uniform lossless line is a causal distributed baseline. PI/SI needs
distributed losses and energy ownership before general lossy extraction and
thermal transfer can be qualified.

## Decision

Add `distortionless_line_transient.py` with a distinct neutral v1 contract
wrapping baseline geometry/source/probe controls and one nonnegative rate.
Explicitly impose Rp=kappa*Lp and Gp=kappa*Cp. Evaluate attenuated delayed
traveling waves and repeated reflections using parent numerical helpers, with
exact zero-rate reduction. Retain separate conductor/dielectric W/m, signed
transported watts, stored J/m, source identity and raw local-loss residuals.
All loss/work/size/precision admission precedes waves; old contracts stay intact.

## Consequences

This is an effective distortionless distributed-circuit model, not arbitrary
lossy RLGC or unconditional full-wave TEM accuracy. Local loss channels support
later ownership/mapping but do not themselves execute thermal deposition.
No dependency, time mesh or fitted delay is introduced. Referenced equations,
independent derivation, validation scope and remaining gates are recorded in the
[method ledger](../DISTORTIONLESS_LINE_TRANSIENT.md).
