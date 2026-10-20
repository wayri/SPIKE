<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0124: physical RLC loaded coupled branches

Status: accepted for experimental development, 21 October 2026.

Add complete physical series-R/L and node-shunt-C source/load assignment on the
4–16 exterior ports of a supplied coupled star. Derive a variable-port conditioned
endpoint solve; retain internal star conditioning and actual strongly bound branch
fields. Preserve terminal/branch heat W separately from mean J and reactive var.

A physical-oracle case revealed a false boundary-integrity rejection near zero
current. Keep the relative criterion and add a limited 64*eps local operand floor
at physical boundaries only. Preserve raw values, other integrity checks and all
power/convergence gates. Independently verify the valid case and above-floor
corruption rejection; document that factor 64 is not a universal error theorem.

Separate strict worker/CLI contracts enforce branch-dependent dimensions. No new
language, dependency, geometric or thermal ownership is introduced. General
physical/board parity and human release review remain open. See
[method and primary sources](../RLGC_LOADED_STAR.md).
