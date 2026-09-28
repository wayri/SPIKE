# SPIKE open-source release plan

This plan covers the SPIKE desktop/CLI and the separate PCB PI `spike-solvers`
repository. FreeCAD workbench development and packaging are outside this
release. The SPIKES circuit engine has its own version and public gate.

## Freeze and publish

1. Freeze the exact SPIKE desktop version and commit. Keep the README badge,
   application manifests, package locks, worker version, release notes, and
   tagged artifact version consistent. Record the exact source revision.
2. Resolve source and test failures. Run architecture, TypeScript, frontend,
   Python, native, package, and installed-worker checks on the frozen source.
   Run at least one documented synthetic simulation for each feature claimed
   in the announcement, with units, validity state, and reproducible inputs.
3. Complete the artifact-specific SBOM, third-party notices and asset
   provenance review. Obtain knowledgeable human review of numerical changes
   and record which workflows remain approximate or unsupported. A disclaimer
   and community feedback request do not substitute for these gates.
4. Produce and verify clean-machine packages and checksums. Tag and publish
   only the exact reviewed commit and artifacts. Label an engineering preview
   as a prerelease; never call it production or physics-signoff qualified.
5. Port selected solver changes into `wayri/spike-solvers` with independent
   API/build review and numerical tests. Its existing MPL-2.0 license and
   versioning remain separate. Follow that repository's release procedure,
   rather than copying SPIKE modules wholesale. The current SPIKE tree has
   conforming DC/mesh, volume PEEC, and native annular/volume kernels that
   have no direct counterpart in the separate library; review contracts,
   import paths, and unit/reference cases during each port.
6. After the release is public and its links work, make one focused community
   post per relevant venue. Reply to reports and move reproducible failures to
   the [structured issue form](https://github.com/wayri/SPIKE-Main/issues/new?template=bug_report.yml).

The current desktop candidate verification is in
[RELEASE_0_3_0_VERIFICATION.md](RELEASE_0_3_0_VERIFICATION.md). The
[PI release qualification](PI_RELEASE_QUALIFICATION.md) and
[public release readiness](PUBLIC_RELEASE_READINESS.md) remain blocking for
their stated scopes.

## Where to post

| Venue | Angle | Timing |
| --- | --- | --- |
| [KiCad.info Community](https://forum.kicad.info/c/community/11) | Ask KiCad users to try the board import, visualization, and issue workflow. Be explicit that SPIKE is an independent companion application. | First, after a usable public preview. |
| [KiCad.info External Plugins](https://forum.kicad.info/c/external-plugins/16) | Use only when the KiCad plugin integration itself is ready and supported; the forum category specifically covers external plugins. | Later, for that integration. |
| [EEVblog EDA forum](https://www.eevblog.com/forum/eda/) | Ask for technical critique of the solver assumptions, units, validation fixtures, and reproducibility. | After source and examples are available. |
| [Show HN](https://news.ycombinator.com/showhn.html) | Demonstrate a runnable, nontrivial artifact with a short explanation and one clear feedback request. | After onboarding and binaries work for strangers. |

The [KiCad forum category descriptions](https://forum.kicad.info/categories)
distinguish Community from External Plugins. Follow the
[forum FAQ](https://forum.kicad.info/faq) and
[Show HN guidelines](https://news.ycombinator.com/showhn.html) before posting.
Do not post a promotional announcement in r/PrintedCircuitBoard: its
[pinned rules](https://www.reddit.com/r/PrintedCircuitBoard/comments/zj6ac8/please_read_before_posting_especially_if_using_a/)
prohibit self-promotion.

## Post content

Use an ordinary engineering tone. Include:

- One sentence on what SPIKE does and a short list of workflows that actually
  run in this release.
- Source, release/download, setup, license, solver-status, and bug-form links.
  State that SPIKE-owned material uses Apache 2.0 and the separate solver repo uses
  MPL-2.0; third-party components retain their own terms.
- Supported platform, KiCad input/version used for the example, and a five
  minute path from install to a visible result.
- Two or three labeled images: imported board, a simulation or trace with
  synthetic/reusable data, and a report or result view. Identify when an image
  is only a UI preview or when analysis was not run.
- Units, solver validity state, reference fixture, relevant error/convergence
  limits, and one concrete result that others can reproduce. Link to the exact
  validation record. Do not call approximate output validated.
- A specific request: try a named workflow, report unclear diagnostics, or
  compare against an independently measured/analytical case. Ask users to
  file a sanitized issue with steps, expected/actual behavior, versions,
  settings, logs, and a minimal permitted fixture.

Draft opening:

> I am developing SPIKE, an offline-first PCB power and signal integrity
> workbench that imports KiCad boards and keeps solver validity visible in its
> results. This is an engineering preview for workflow and reproducibility
> feedback. The linked example uses a redistributable board and records its
> exact input, units, and current solver limits. I would value reports on
> import fidelity, confusing diagnostics, and small numerical cases with an
> independent reference. Please use the structured issue form and remove
> private board data before posting.
