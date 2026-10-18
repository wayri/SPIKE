<!-- SPDX-License-Identifier: Apache-2.0 -->
# Numerical method evidence policy

Applies to future physics-affecting implementation and changes across all SPIKE
domains, including compact models, material laws, coupling, postprocessing,
surrogates and acceleration. This implements the user's requirement for
established mathematics/physics, subject knowledge, explicit references and
carefully evaluated frontier research. Existing provenance/validation gaps remain
open; this policy does not retroactively qualify or invent lineage for old code.

Use the [method evidence template](templates/numerical-method-evidence.md),
[solver mathematics map](SOLVER_MATHEMATICS.md),
[reference ledger](SOLVER_REFERENCES.md) and
[clean-room policy](RESEARCH_AND_CLEAN_ROOM_ENGINEERING.md).

## Required chain from claim to evidence

Every numerical feature/change must link:

1. **Physical question and observable.** Domain, supported scales/regimes,
   dimensions, units, frames, geometry/material assumptions and intended outputs.
2. **Governing mathematics and primary references.** Conservation/constitutive
   equations, initial/boundary/interface conditions, approximations and a source
   with author/publisher, title, year/revision, DOI/official URL and reviewed
   equation/section/page. Original derivations still cite their relevant physical
   and mathematical foundations. Distinguish an abstract/scope check from actual
   method/full-text review; unavailable details stay unresolved.
3. **Independent formulation.** Derive strong/weak/discrete forms or compact-model
   equations in project notation, including tensor/shear/sign conventions,
   nondimensionalization/scales, conserved energy/work/charge and dissipation.
   Explain why the method fits the physical regime and what is omitted.
4. **Numerical analysis.** State spaces/operators, nullspaces/constraints,
   nonlinear tangents, conditioning/scaling, time/mesh/frequency controls,
   stability/convergence assumptions, positivity/passivity where applicable,
   stopping tolerances and resource/failure/cancellation limits.
5. **Executable verification.** Independent analytical/manufactured/oracle cases,
   invariant/unit/frame checks, refinement and meaningful adversarial/rejection
   controls. Set observable-specific tolerances before accepting results.
   Tests that merely re-execute the implementation's own formula are insufficient.
6. **Physical validation and uncertainty.** Admitted independent measurements,
   calibration/held-out separation, geometry/load/material matching, measurement
   uncertainty, model-form limits and discrepancy. Synthetic correctness alone
   cannot establish physical predictive accuracy or life qualification.
7. **Traceable delivery.** Bind source, input/mesh/material/model/backend/code
   revisions, raw outputs, logs, references and actual test evidence to the bounded
   claim. Record performance at equal error, including all relevant overhead.

The [NASA NPARC V&V tutorial](https://www.grc.nasa.gov/www/wind/valid/tutorial/tutorial.html)
is a primary guide for distinguishing code/solution verification, convergence
and validation in CFD; adapt the evidence to each domain. Measurement uncertainty
should have a stated treatment, with [NIST TN 1297](https://www.nist.gov/pml/nist-technical-note-1297)
as a reference for expression of measurement uncertainty. Neither document proves
any particular SPIKE result or substitutes for domain-specific requirements.

## Research versus established use

Established governing laws do not automatically validate a new discretization,
closure, constitutive fit or coupling algorithm. A research implementation must
name its candidate status, additional assumptions and comparison reference.
Peer review is useful evidence, not automatic applicability. Preprints stay
explicitly identified. Unproven behavior must remain experimental/unsupported
even when an interface, plot or demonstration runs successfully.

For learned surrogates record training-data generation/rights, leakage controls,
distribution shifts, conservation/stability and uncertainty/abstention behavior.
For differentiation record gradient tests and nonsmooth regimes. For accelerated
or reduced execution record precision, approximation error and complete runtime/
memory against the unchanged problem. Residual size, visual plausibility,
conservation alone or agreement between two codes cannot establish all accuracy.

## Review, references and honest promotion

Subject-matter review must assess physical regime, equations, empirical laws and
failure interpretation; numerical review assesses discretization, conditioning
and error. Record the extent of each review. Agent review is supporting evidence;
knowledgeable human numerical review before release remains mandatory under
CONTRIBUTING.md. This requirement does not block bounded development.

References are attached to precise methods/claims, not presented as a generic
proof by bibliography. Public product pages establish advertised feature scope;
they do not establish numerical correctness. A licensed standard is normative
only after its actual applicable revision/clause has been reviewed. A citation
does not grant copying, dataset/model redistribution or dependency integration
rights. Follow clean-room and licensing rules.

Keep source fact, independently derived result, assumption, computed result and
engineering recommendation distinct. Later-added corroborating references must
not be described as sources used during an earlier implementation. Missing
lineage remains a tracked gap. Existing reference indexing checks recorded links,
not scientific truth or whether a paper was read.

Mark a bounded stage Done only against its declared executed acceptance evidence;
keep broader family gaps and production qualification separate. Update the
mathematics, references and solver-status records together when numerical
capabilities or validity limits change.
