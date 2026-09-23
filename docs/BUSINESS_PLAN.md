# SPIKE Business Plan

## Executive decision

SPIKE should be developed as an open-core engineering product with a free local desktop edition, paid professional capabilities, and optional hosted execution. The first commercial wedge is power-integrity triage and reporting for KiCad and standards-based PCB data. The product should not initially claim to replace enterprise 3D EM suites.

The business is viable if SPIKE earns trust through validated results and converts engineering time saved into paid subscriptions, support, and services. The primary risk is not that AI makes software cheaper; it is that an unvalidated simulator is not trusted for design decisions. Validation, import fidelity, reproducibility, and support are the durable assets.

## Customer segments

| Segment | Problem | Initial offer | Buying trigger |
|---|---|---|---|
| Small hardware teams | PI issues discovered late; enterprise tools too expensive | Local PI desktop and reports | First failed prototype or EMI/thermal review |
| KiCad professionals | No integrated, accessible PI workflow | KiCad import adapter plus standalone analyzer | High-current or high-speed board review |
| Consultants and labs | Need repeatable analysis and client deliverables | Pro reports, batch CLI, project templates | Multiple boards per month |
| Universities and labs | Need inspectable numerical methods | Open core, fixtures, teaching examples | Course, grant, or lab adoption |
| Larger engineering teams | Need traceable CI and shared validation | Team/CI/cloud plan | Design review or release gate |

## Product ladder

### Free Community

- Standalone local application.
- Optional KiCad import and launch adapter.
- Supported standards importers as released.
- Basic DC PI.
- Limited AC inspection.
- Open project and result schemas.
- Examples and validation fixtures.
- Community support.

### Professional

Indicative starting price: **$39-$99 per engineer per month**, or **$399-$999 per year**.

- Broadband AC and parasitic extraction.
- SPICE and Touchstone export.
- Advanced probes and batch analysis.
- Revision comparison.
- Automated reports.
- Higher mesh and design-size limits.
- Priority support.

### Team

Indicative starting price: **$299-$999 per team per month**.

- Shared projects.
- CI/headless execution.
- Review links and result history.
- Organization limits and policies.
- Private package repositories.
- Team support and onboarding.

### Enterprise and services

- Private deployment.
- Custom importer or solver work.
- Validation against customer hardware.
- Training and engineering consulting.
- Support agreements.
- Certified or customer-audited reports.

Services should fund early development but must not become the only revenue source. Reusable improvements should be moved into the product and documented.

## Revenue model

Use a mixed model:

1. Individual subscriptions for advanced local capability.
2. Team subscriptions for collaboration and CI.
3. Hosted compute for expensive sweeps and future full-wave workers.
4. Paid support and validation services.
5. Sponsorships and grants for open infrastructure.
6. Training, workshops, and reference designs.

Illustrative base case after product-market fit:

| Year | Paid individuals | Teams | Services/sponsors | Approx. gross revenue |
|---|---:|---:|---:|---:|
| 1 | 100 | 5 | $25k | $75k-$150k |
| 2 | 500 | 25 | $75k | $300k-$600k |
| 3 | 1,500 | 75 | $200k | $1.0m-$1.8m |

These are planning scenarios, not forecasts. The most important validation is conversion from active monthly users to paid users and renewal after the first real board review.

## Unit economics

Track these metrics from the first public release:

- Monthly active projects.
- Time from import to first completed analysis.
- Percentage of imported designs with unresolved issues.
- First-analysis completion rate.
- Weekly retained engineering users.
- Free-to-paid conversion.
- Paid renewal and expansion.
- Cost per support case.
- Hosted compute cost per analysis.
- Gross margin by plan.
- Percentage of services work converted into reusable product capability.

Target direction:

- Local Professional gross margin above 85%.
- Hosted compute gross margin above 60% after optimization.
- Services gross margin above 40% while productizing repeated work.
- Annual retention above 75% for teams.
- Payback period below 12 months for enterprise acquisition.

## Cost structure

Primary costs will be engineering time, numerical validation, cross-platform packaging, support, cloud compute, licensing/compliance review, and hardware measurement.

Keep the first commercial architecture local-first to minimize recurring infrastructure costs. Cloud should be optional and metered only when it creates clear value. Avoid storing customer designs by default.

## Go-to-market

### Stage 1: credibility

- Publish analytical validation fixtures.
- Publish limitations and accuracy tables.
- Release a KiCad walkthrough using an open board.
- Demonstrate a complete import-to-report workflow.
- Recruit five design partners.

### Stage 2: practitioner adoption

- Target KiCad forums, KiCon, open hardware communities, university labs, consultants, and power electronics communities.
- Publish failure-focused technical articles: return paths, plane neck-downs, decoupling resonance, connector bottlenecks, and current-density hotspots.
- Offer free report generation for public/open-source boards.

### Stage 3: conversion

- Gate advanced extraction, batch, CI, and team history behind Professional/Team plans.
- Sell validation and onboarding to consultants and small hardware companies.
- Convert successful design partners into case studies.

## Open-source and sponsorship strategy

Keep the open contract, parser interfaces, basic DC path, examples, and validation fixtures public. Place advanced hosted execution, enterprise administration, and paid support around the open core.

Do not depend on sponsorship for payroll. Treat sponsors as funding for public infrastructure: importer support, benchmark hardware, documentation, and university programs. KiCad publishes corporate sponsorship tiers from $1,000 Bronze to $15,000 Platinum annually, which demonstrates a relevant ecosystem funding mechanism. [KiCad sponsorship](https://www.kicad.org/sponsors/become-a-sponsor/)

Create sponsor benefits that do not compromise technical independence:

- Publicly documented benchmark fixture sponsorship.
- Named support for standards importer work.
- Hardware measurement program sponsorship.
- University and conference grants.
- Recognition on the project site without preferential solver results.

## Main risks and mitigations

| Risk | Consequence | Mitigation |
|---|---|---|
| Results are not trusted | No professional conversion | Public fixtures, measurements, convergence, and limitations |
| Importers silently lose geometry | Wrong analysis | Import-quality report and unresolved-object warnings |
| Scope expands into a full EDA suite | Long delay and weak product | Keep PI/SI analysis as the product boundary |
| Cloud costs grow faster than revenue | Negative margin | Local-first execution and metered hosted jobs |
| Open-core boundary alienates contributors | Forks or low adoption | Keep public schemas and basic engine useful; document license policy |
| One founder becomes support bottleneck | Slow growth | Reproducible diagnostics, logs, docs, and paid support tiers |
| AI-generated code increases defects | Numerical regressions | Human-reviewed solver changes and mandatory validation gates |

## Business gates

Do not make major commercial commitments until these gates are met:

- Gate A: 10 reproducible public validation cases.
- Gate B: 5 design partners complete a real board review.
- Gate C: 100 active monthly community users.
- Gate D: 10 paying users or 2 paying teams.
- Gate E: paid renewals demonstrate repeated value.
- Gate F: hosted compute is profitable per job before broad cloud launch.
