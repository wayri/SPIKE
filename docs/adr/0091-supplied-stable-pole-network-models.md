# ADR 0091: Supplied stable-pole network models

Status: accepted for bounded experimental development; release qualification open.

## Context

Sampled network preparation alone does not provide a reusable rational model.
Unconstrained complex fitting can introduce unstable or non-real models and
hide poor source reconstruction behind a successful least-squares call.

## Decision

Fit real direct/residue matrices at explicit negative real poles using a
column-equilibrated full-rank real least-squares system. Require declared
sample-error tolerance and preserve source identity, coefficients, realization
and numerical diagnostics. Keep active models without passivity repair.

## Consequences

The supplied-pole model is proper, real and stable by construction, with
bounded fit evidence. It does not establish source causality or general
broadband accuracy. Automatic pole selection, passive fitting and transient
integration retain separate stages. No dependency or language is added.
