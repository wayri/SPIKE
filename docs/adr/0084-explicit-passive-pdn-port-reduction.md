# ADR 0084: Explicit passive sampled PDN port reduction

Status: Accepted for bounded development; human numerical review before release.

## Decision

Add a separate Python module and request/result contracts to eliminate explicitly
terminated auxiliary ports from sampled admittance networks. Preserve an exact
ordered partition, source/reference/context identities and model status. Require
passive source and termination samples; zero termination means floating ports.
Use conditioned direct Schur solves and independent conjugate power accounting,
with no repair or regularization. Reciprocity is not required.

The existing owned worker exposes `reduce_pdn_admittance`; the finite-dielectric
projection helper copies samples into this boundary. No new dependency, language
or automatic transient-network attachment is introduced. The existing PDN and
dielectric APIs remain compatible.

## Acceptance and limits

Original circuit, power, ordering, rejection/resource/cancellation and actual
extraction-to-worker checks define PI02-S02 acceptance. See
[derivation and scope](../PDN_ADMITTANCE_REDUCTION.md). Sampled passivity does not
establish causality, interpolation, measured validity or a dynamic macromodel.
