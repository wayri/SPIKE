# SPIKE Licensing and Provenance Policy

SPIKE has a mixed-license repository boundary. Do not treat the root
`LICENSE` as a grant for every file, dependency, model, fixture, asset, or
external runtime in this workspace.

## Repository obligations

- Preserve each file's SPDX identifier, copyright notice, and applicable
  source license.
- Record the source, owner, license expression, redistribution status, and
  required notices for every new dependency, binary, model, board, screenshot,
  icon, font, dataset, or other redistributed asset.
- Do not copy third-party code, artwork, model data, documentation, or fixtures
  without a recorded right to use and redistribute them.
- Keep optional external engines under their upstream terms. Customer-provided
  proprietary tools are never bundled, downloaded, or used beyond permitted
  automation rights.
- Generate the final distribution's SBOM and notice bundle from verified
  artifacts. `THIRD_PARTY_NOTICES.md` is the release-blocking provenance
  register until its entries are resolved.

## Contributions

New contributions require a Developer Certificate of Origin or a contributor
agreement selected by the project owner. New source files require an approved
SPDX identifier after the ownership and license boundary have been reviewed.

`LICENSE` records the repository license text. `THIRD_PARTY_NOTICES.md` records
external obligations and provenance; neither document grants rights that its
underlying evidence does not establish.
