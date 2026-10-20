<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR 0112: explicit finite SI candidate and corner studies

Status: accepted for experimental development, 2026-10-19.

SPIKE already solves loaded supplied SI networks. Pre-layout exploration needs
reproducible comparisons that cannot silently omit an unsuccessful corner or
mistake sampled gain for protocol compliance.

Add an orchestration boundary `run_si_candidate_study` using the unchanged
`run_si_workflow` solver for complete explicit scalar RLGC candidate×corner
populations. Retain child inputs/results/digests and compare supplied sampled V/V
bounds. The existing network worker and CLI own execution. Strict schemas,
bounded resource admission, cancellation between child solves and independent
loading references define the public contract. No numerical kernel, language or
third-party dependency is introduced.

Failed/partial corners remain visible and prevent candidate passage. Experimental
results report exact sampled witnesses and preserve model temperatures for later
multiphysics work, without inventing physical heat or material feedback. General
topology editing, geometry extraction, layout constraint export, nonlinear SI,
continuous-band compliance and physical validation remain separate work.

See [method, references and limits](../SI_CANDIDATE_STUDY.md). Human numerical
review remains required before release.
