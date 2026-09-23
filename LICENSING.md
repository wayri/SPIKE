# SPIKE Licensing Policy

## Current Status

SPIKE uses a mixed-license boundary. There is no safe basis in this workspace
for declaring the entire repository MIT or proprietary: repository history is
unavailable, some work declares MIT, and external solver integrations include
reciprocal and mixed-license software.

The intended product structure is:

| Boundary | Intended terms | Status |
| --- | --- | --- |
| Public schemas, exchange contracts, importer SDK, conformance fixtures | MIT, after ownership confirmation | Provenance review required |
| Existing MIT files and contributions | MIT | Preserve notices and source grant |
| Native SPIKE commercial solver and advanced workflow modules | Commercial EULA | Candidate only after ownership confirmation |
| Desktop binary distribution | Commercial EULA plus third-party notices | Draft, not approved for sale |
| Process-isolated external solvers | Upstream terms; optional SPIKE adapter terms | Per-engine review required |
| Customer-provided proprietary tools | Vendor terms plus SPIKE connector terms | Never bundled without written permission |

The commercial EULA never overrides third-party or existing open-source terms.

## Commercial License Classes

SPIKE supports the following entitlement classes. Product availability and
numerical validation remain independent of license entitlement.

| Class | Duration | Activation | Intended use |
| --- | --- | --- | --- |
| Evaluation | Fixed short term | One named user and one registered device | Product evaluation; no production reliance |
| Professional | Subscription or fixed term | One named user and one registered device | Commercial engineering use for licensed modules |
| Enterprise | Contract term | Named-user/device or organization-managed seats | Team policy, CI, support, and licensed enterprise modules |
| Developer | Short-lived signed entitlement | Approved developer identity and registered device | All implemented capabilities, diagnostics, fixtures, and extension development |

A license may authorize a capability; it does not convert an approximate,
experimental, unsupported, or unvalidated solver into a validated solver.

## One-User, One-Machine Rule

The production control is server-side activation plus a device-key proof, not a
JavaScript flag or a reusable key stored on disk:

1. A purchase or invitation is assigned to one named user.
2. The native host generates a non-exportable device key in the OS credential
   store and sends only its public-key digest during activation.
3. The licensing service permits one active device for the license unless the
   commercial order explicitly grants more seats.
4. The service signs an entitlement containing the subject, device binding,
   capabilities, product version, validity window, activation ID, and revocation
   epoch.
5. The Rust host verifies the signature and device proof at startup and before
   every protected native operation.
6. Deactivation releases the seat. Lost-device recovery invalidates the prior
   activation and is auditable.

Offline activation is a signed request/response exchange. It can bind a license
to a device, but strict concurrent-seat enforcement requires periodic contact
with the licensing service.

## Required Release Gate

No commercial installer may be published until all items below are complete:

- Recover authoritative Git history and contributor records.
- Confirm ownership or written permission for every proprietary candidate.
- Obtain contributor agreements or rewrite disputed material where needed.
- Complete the licensor identity, address, governing law, venue, support terms,
  and privacy references in the EULA.
- Inventory every dependency, binary, model, board, screenshot, icon, font, and
  documentation asset with source, version, license, owner, and redistribution
  evidence.
- Remove unapproved external runtimes from the commercial package.
- Produce an SBOM, third-party notices, corresponding-source offers where
  required, and signed hashes for all distributed artifacts.
- Implement native entitlement verification and capability enforcement.
- Ensure production builds contain no unsigned development bypass and accept
  developer access only through a signed, named, device-bound entitlement.
- Code-sign and timestamp the installer and application binaries.
- Complete IP, export-control, privacy, consumer-law, and warranty review with
  qualified counsel.

## Contribution Policy

New contributions require a Developer Certificate of Origin or an executed
contributor agreement selected by the project owner. Every new source file must
carry an approved SPDX identifier. Contributions must not copy reference-product
code, artwork, screenshots, proprietary model data, or documentation.

## Documents

- Commercial terms: `licenses/SPIKE-COMMERCIAL-EULA-DRAFT.md`
- Entitlement contract: `schemas/license-entitlement-v1.schema.json`
- Enforcement design: `docs/LICENSE_ENGINE_ARCHITECTURE.md`
- User and tier model: `docs/LICENSING_AND_USERS.md`
- External obligations: `THIRD_PARTY_NOTICES.md`
