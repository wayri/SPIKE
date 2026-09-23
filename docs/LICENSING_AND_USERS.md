# Licensing, Users, and Capability Enforcement

## Authority

The repository-wide policy is `LICENSING.md`; commercial terms are drafted in
`licenses/SPIKE-COMMERCIAL-EULA-DRAFT.md`; and the signed entitlement contract is
`schemas/license-entitlement-v1.schema.json`. This document describes product
users and capability behavior and does not itself grant a source-code license.

## Development Release

The current source build is the root development release. It does not contain an
unsigned developer bypass. The React UI reads a native, read-only license
summary from the Rust host; protected worker operations are mapped to explicit
capabilities and denied when no valid entitlement grants them. An unlicensed
desktop remains in viewer/recovery mode and can inspect permitted project data.

Developer access uses the same Ed25519-signed entitlement envelope as every
other class. A developer entitlement must be named, bound to the current
machine and operating-system user, time limited, and issued by an approved
offline issuer or licensing service. Browser storage holds preferences and
display identity only and is never an authorization boundary.

The current offline implementation verifies signatures, product compatibility,
validity time, claims, and the machine/user binding. It prevents a signed
entitlement copied to a different machine or user from working. Strictly
preventing two valid entitlements from being issued for the same commercial
seat requires the planned server-side atomic activation and revocation service.

## User Types

| User type | Intended scope |
| --- | --- |
| Viewer | Open projects and reports; inspect validated result bundles |
| Engineer | Configure and run licensed analyses; save projects and exports |
| Administrator | Manage organization policy, solver trust, model libraries, and licenses |
| Developer | Load development extensions, run verification fixtures, and access experimental capabilities |

## Product Tiers

| Tier | Intended capability boundary |
| --- | --- |
| Community | Import, project model, basic DC, probes, CLI, validation fixtures, HTML report |
| Evaluation | Signed, short-lived evaluation of specifically listed capabilities; not for production reliance |
| Professional | Advanced PI, broadband extraction, SPICE integration, revision comparison, production reports |
| Enterprise | Organization policy, CI, shared validation baselines, support, and certified packages where available |
| Development | All feature flags, diagnostics, experimental solvers, and extension development |

The current implementation does not hide unfinished physics behind a license. A capability can be licensed and still unavailable because its solver is absent or its validation gate has not passed. License state, installed capability, and model validity are separate axes.

## Production License Requirements

1. Licenses are signed claims verified in Rust, not JavaScript.
2. Claims contain license ID, licensee, tier, capabilities, issue time, expiry, product major version, and optional machine or organization binding.
3. SPIKE ships only the public verification key.
4. Offline verification is supported; routine application use does not require a licensing server.
5. Clock rollback and corrupted claims produce an explicit restricted state, never silent deletion of user data.
6. Project files do not contain reusable license secrets.
7. Exported reports record the product version and entitlement class but not private license material.
8. Extension and solver trust uses an independent signature and permission model.

## Current Implementation Boundary

Implemented in the desktop host:

- signed Ed25519 entitlement verification with a build-pinned issuer key;
- temporary, timed, perpetual, and developer license types;
- evaluation, professional, enterprise, and developer tiers;
- machine-and-user binding, activation, local deactivation, and offline device
  request export;
- deny-by-default viewer state and capability checks at the generic worker
  boundary; and
- canonical security error codes with redacted diagnostics.

Required before a commercial production release:

- OS-protected device-key storage and proof of possession;
- server-side one-seat assignment, refresh, deactivation, revocation, recovery,
  and clock-rollback policy;
- capability checks on every native command and export path, not only the
  generic worker boundary;
- issuer-key rotation, security review, abuse/race testing, and penetration
  testing; and
- a legally approved EULA and code-signed installer.

## Open-Core Boundary

The repository contains MIT-licensed work and material whose ownership cannot be
proven from this workspace because Git history is unavailable. Existing grants
cannot be silently relicensed. A commercial boundary requires recovered history,
ownership evidence, clearly separated modules, clean dependency declarations,
contributor agreements where appropriate, and a published compatibility policy.

## Commercialization Gate

Commercial deployability is a mandatory design constraint, not a release-time
cleanup task. Every dependency, solver, model library, dataset, icon, font, and
generated asset must have a recorded owner, version, source, license, linking
mode, redistribution right, hosted-service right, notice obligation, and
replacement plan before it enters a distributed build.

The default integration policy is:

1. Keep the MIT/open-core desktop, schemas, worker contracts, and proprietary
   modules free of copied or linked reciprocal-license implementation code.
2. Integrate GPL and similarly reciprocal solvers through versioned files or
   process IPC and package each linked adapter under terms compatible with its
   upstream license. Process isolation is an engineering boundary, not by
   itself a legal exemption; redistribution still requires review and all
   applicable source, notice, and dependency obligations.
3. Do not require a non-redistributable dependency for core offline use. Offer
   customer-provided licensed connectors only when the vendor license and API
   explicitly permit that workflow.
4. Keep proprietary model libraries, certified fixtures, hosted services, and
   commercial extensions behind stable public contracts so the open core and
   third-party solvers remain replaceable.
5. Do not copy source, artwork, documentation, screenshots, model data, or UI
   assets from reference products. Published mathematics, standards, and
   independently implemented workflows require source attribution and a clean
   implementation record where appropriate.
6. Generate an SBOM and third-party-notice bundle for every installer and
   portable package. Block release when a dependency has unknown provenance,
   incompatible terms, missing notices, or no approved distribution route.
7. Review desktop redistribution, cloud/SaaS use, CI/container deployment,
   export controls, trademarks, patents, and customer-data handling separately;
   permission in one deployment model does not imply permission in another.
8. Prefer dependencies with stable cross-platform builds, documented APIs,
   reproducible packaging, active maintenance, and a credible replacement path.

Legal conclusions remain subject to qualified counsel. Engineering metadata
must preserve enough evidence for that review instead of assuming that an
open-source label automatically permits commercial bundling.
