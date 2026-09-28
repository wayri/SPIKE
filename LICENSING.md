# SPIKE Licensing and Provenance Policy

## License boundary

Original SPIKE-owned source code, documentation, and original SPIKE screenshots
and media in this repository are licensed under the standard Apache License 2.0
in [LICENSE](LICENSE), unless a file or subtree states a different license.
This change covers SPIKE Main only. It does not change the separate
`spike-solvers` repository, the independently versioned SPIKES circuit engine
(`python/spikes`, `standalone/spikes_project`, and `SPIKES-Independent`), or
the FreeCAD workbench under `integrations/freecad`.
Apache 2.0 permits commercial use, sale, modification, redistribution, and use
in a hosted service. It does not require source disclosure for modifications
or a hosted service. Recipients receive those rights too. Redistribution must
carry the license, preserve applicable notices, and mark modified files.

A SPIKE screenshot may display a third-party board, model, or other asset. Apache 2.0
covers only SPIKE-owned elements; embedded material retains its upstream
rights and notices. File-level SPDX identifiers and third-party licenses take
precedence over this repository default. External libraries, solvers, runtimes,
fixtures, board designs, models, fonts, and other third-party material are not
relicensed by SPIKE. Review [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
and each original license before distribution. Apache 2.0 does not grant rights to
the SPIKE name or marks.

SPIKE may later sell Apache-licensed builds, support, integration, or hosted
services. It may also keep new, separately authored modules private, subject
to existing grants and dependency obligations. Apache-licensed contributions
cannot later be made exclusive without their authors' separate permission.
Earlier valid MIT grants remain in force; their text is retained in
[licenses/MIT.txt](licenses/MIT.txt). This change does not relicense material
owned by someone else.

## Repository and release obligations

- Preserve each file's SPDX identifier, copyright notice, and applicable
  license. Existing MIT grants remain in force.
- Record the source, owner, license expression, redistribution status, and
  required notices for every dependency, binary, model, board, screenshot,
  icon, font, dataset, or other redistributed asset.
- Do not copy third-party code, artwork, model data, documentation, or fixtures
  without a recorded right to use and redistribute them.
- Keep optional external engines under their upstream terms. Customer-provided
  proprietary tools are never bundled, downloaded, or used beyond permitted
  automation rights.
- Generate the final distribution's SBOM and notice bundle from verified
  artifacts. Open items in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
  remain release-blocking for affected packages. The Apache grant for SPIKE-owned
  material is not redistribution approval for external material.
- Complete the project owner and knowledgeable legal review required by the
  public release gate before publishing source or binaries. Verify the exact
  artifact against its included licenses, notices, and components.

## Contributions

Contributions to Apache-licensed SPIKE files are submitted under Apache 2.0 unless an
explicitly marked different license is accepted by the maintainers. Each
commit must carry the Developer Certificate of Origin sign-off described in
[CONTRIBUTING.md](CONTRIBUTING.md). The sign-off records the contributor's right
to submit; it does not transfer copyright or override an upstream license.
New source files require an approved SPDX identifier and ownership review.
A change to a file's license requires an explicit project decision and any
necessary rights from its authors.
