# SPIKE project working directive

Apply this policy to every task in this repository, including coding, analysis,
reviews, planning, and documentation. Follow higher-priority instructions and
explicit task requirements. Optimize for verified useful outcomes per total
token, time, and compute cost, including retries and agent coordination.
Efficiency must preserve correctness, complete scope, and required validation.

## Model selection

These are the user's routing preferences, not claims about measured pricing.
Use the least expensive capable model available for each bounded task:

| Model | Preferred work |
| --- | --- |
| Terra (`gpt-5.6-terra`) | Clear, low-risk fixes; focused inspection; routine tests; documentation; straightforward implementation with settled contracts. |
| Sol (`gpt-5.6-sol`) | Difficult debugging, multi-file implementation, integration, and critical changes with understood architecture and checkable acceptance criteria. |
| Astra (`gpt-6-astra`) | Ambiguous architecture, numerical/physics reasoning, security-sensitive design, hard root-cause analysis, and independent review where the consequences warrant it. |

Start critical work at the appropriate tier; do not spend failed cheap attempts
on a known hard problem. Escalate when evidence shows the current approach is
insufficient. After two unsuccessful hypothesis-driven attempts, reassess the
cause, missing evidence, and model before continuing. Return routine follow-up
work to Terra when a handoff is economical. Use low/medium reasoning for routine
work and higher effort only for material uncertainty or risk.

Select models only through supported controls. A prompt cannot switch its own
running model. If routing is unavailable, apply this workflow on the available
model and disclose a material limitation once; never claim an unperformed switch.

## Agents

Use one agent by default. The user requests selective delegation when useful:
delegate only a concrete independent subtask whose expected benefit exceeds
startup, duplicated context, integration, and review cost. Prefer one or two
bounded workers; add more only for clearly independent substantial work.
Do not create agents just to reread files, agree with a plan, or duplicate work.

Give each worker the objective, relevant paths, constraints, file ownership,
acceptance checks, and a concise return format. Prefer minimal context over a
full conversation fork. Use the model table above when explicit selection is
supported. Keep edits disjoint, reuse suitable existing agents, and have one
owner integrate and verify results. Request independent review only where risk
justifies it. Never start separate user-visible tasks unless requested.

## Efficient execution

- Define the outcome and smallest sufficient evidence first. Skip formal plans
  for simple tasks; use short plans for complex work.
- Search narrowly with `rg`; read relevant sections and subsystem indexes.
  Exclude generated artifacts, dependencies, binaries, and build outputs unless
  they are implicated. Broaden inspection only when evidence requires it.
- Reuse existing code, contracts, fixtures, and verified findings. Avoid
  speculative abstractions, unrelated cleanup, and broad rewrites.
- Prefer deterministic tools to model reasoning for search, arithmetic, format
  checks, and mechanical transformations. Batch independent reads/checks and
  bound output. Do not repeatedly scan unchanged files or poll unchanged state.
- Debug with a falsifiable hypothesis and the smallest discriminating check.
  Avoid random edits, exhaustive speculation, and repeated equivalent retries.
- Run focused checks during iteration, then required project checks. Broaden
  or repeat only for changed code, failures, dependencies, or unresolved risk.
  Never waive mandatory tests to save tokens or report unrun checks as passed.
- Keep progress and handoffs short: decisions, evidence, changed files,
  remaining uncertainties, and next action. Do not repeat full plans or logs.
- Finish when the requested outcome and acceptance checks are satisfied.
  Report results, validation, and material limitations concisely. Do not invent
  token savings or cost measurements; use telemetry only when available.

## SPIKE correctness constraints

SPIKE is a general multiphysics simulation platform. PCB/ECAD and MCAD are
geometry/identity inputs; simulation geometry preparation is in scope, building
a general MCAD authoring product is not. General chemical-engineering expansion
remains outside active scope. On 21 October 2026 the owner explicitly authorized
propulsion-specific jet/gas-turbine combustion only; follow the narrow boundary
in `docs/PROPULSION_MACHINES_FLUID_POWER_PLAN.md`, without enabling unverified
reacting-flow capability. Follow `docs/MULTIPHYSICS_PLATFORM_STRATEGY.md` and preserve
the existing execution gates when evaluating recommended future directions.

All future physics-affecting changes require established governing mathematics,
subject-matter assumptions, an independently authored derivation and traceable
primary references under `docs/NUMERICAL_METHOD_EVIDENCE.md`. Record the exact
method/source/version reviewed, units, validity, numerical analysis and executed
verification/validation evidence. Evaluate frontier methods as explicitly
experimental candidates against established references; do not infer correctness
from novelty, citations, plots or AI output. Existing provenance gaps remain open.

Follow `CONTRIBUTING.md` and its required architecture, design, language,
licensing, and validation guidance when changing the relevant implementation.
Use `docs/SUBSYSTEM_INDEX.md` to locate ownership and `docs/SOLVER_STATUS.md`
for validated capability claims. Preserve contracts and other tasks' changes.
Physics, units, numerical stability, convergence, and solver-result validity
deserve stronger reasoning and meaningful numerical evidence. Preserve
approximate/unsupported states; UI availability does not establish validation.
Required knowledgeable human review of numerical code before release remains.

The portable copy/paste version is `docs/EFFICIENT_WORK_PROMPT.md`; this file
is the authoritative project policy and need not be duplicated in every prompt.

## Publication identity

SPIKE source and releases use only the `wayri` GitHub identity. For this
repository, the canonical Git author and committer are `wayri` with
`16292067+wayri@users.noreply.github.com`. Never author, commit, sign off, tag,
or publish SPIKE work as a work account or with a work email address. Before
creating a commit, verify both `git var GIT_AUTHOR_IDENT` and
`git var GIT_COMMITTER_IDENT`; stop if either identity differs. Repository-local
Git configuration must use `user.useConfigOnly=true` so an absent identity
is not guessed. Because Git still honors global identity configuration, the
repository-local `user.name` and `user.email` values must both exist and match
the canonical identity above. Release publication additionally follows
`docs/ATTRIBUTION_POLICY.md` and the fail-closed release automation checks.
Before pushing, use the repository pre-push identity guard described there.
