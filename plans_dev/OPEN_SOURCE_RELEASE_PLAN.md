# SPIKE staged open-source release plan

Planning date: 2026-09-20. Status: proposal, not a release authorization or a
claim that current implementations are qualified. This is an INTERNAL planning
record: it names withheld material and must not enter either public repository.

This proposal supersedes `COMMUNITY_RELEASE_STRATEGY.md` for this release's
planning. It does not change current development code, licenses, release gates,
or ownership records. Execution starts after the internal development freeze.

## 1. Outcome and commercial rationale

Release a useful, offline KiCad engineering application with the existing main
UI, qualified PI workflows, portable projects/results, reports, and documented
extensions. Publish its eligible numerical engine as a separate reusable
project. Add SI and then thermal through separately qualified releases.

The valuable assets are the integrated board-to-result workflow, reliable
geometry and units, reproducible numerical evidence, portable results,
visualization, and a stable extension/API ecosystem. Source volume, UI breadth,
and passing unit tests alone do not establish a commercial valuation. No
revenue, customer demand, ownership-complete inventory, or independently
qualified production performance has been established by this planning audit.
Consequently a dollar valuation would be speculative.

Recommended business sequence:

| Mechanism | Offer | Evidence needed before scaling |
| --- | --- | --- |
| Services and training | KiCad PI onboarding, workflow integration, training, bounded engineering studies | Repeatable supported workflow, clear analysis limits, paid pilot demand |
| Sponsored development | Customers fund public bug fixes, supported workflows, benchmarks, documentation | Written scope, acceptance criteria, ownership and publication terms |
| Support subscriptions | Supported releases, response commitments, migration assistance, long-term maintenance | Maintainer capacity, support economics, reliable regression suite |
| Commercial UI and extensions | Additional proprietary team workflows, integrations and productivity tools using public contracts | License-compatible boundaries and differentiated customer value |
| OEM integration | Embed the solver/workflows with integration support or negotiated rights | Stable API/ABI, redistribution inventory, qualification and support commitments |
| Sponsorship and research funding | Maintenance, reproducibility, teaching and public validation work | Public evidence and funding eligibility; treat donations as supplementary |
| Optional hosted execution | Later, separately offered managed compute | Demand, cost and confidentiality controls; community desktop stays offline-capable |

Measure repeat use, successful reproducible analyses, time saved, support hours,
paid pilot conversion, and recurring contract retention. Separate replacement
cost, sale value of IP, and potential business revenue; they are different.
Do not claim parity with commercial signoff products without relevant evidence.

## 2. Release scope

There are TWO projects and THREE desktop distribution artifacts (two Windows
forms and one Linux form), rather than two binary variants.

| Stage | Public desktop scope | Entry gate |
| --- | --- | --- |
| 1: PI | KiCad import; main 2D/3D UI; qualified DC conductor and frequency-domain AC/PDN work; probes, history, reports, existing applicable exports; SDK/extensions | Explicit feature inventory and numerical qualification for every advertised workflow |
| 2: SI | Stage 1 plus individually qualified SI workflows | All retained PI regressions pass; additive contracts and result compatibility |
| 3: thermal | Stages 1-2 plus individually qualified thermal workflows | PI/SI regression gates and thermal conservation/convergence/correlation evidence |

Interpret "full PI" as all approved PI functionality inside this expressly
bounded public scope. It cannot mean the existing internal full-PI definition,
which requires SPICE, transient analysis and iterative field/circuit coupling.
Externally describe the actual DC/frequency-domain scope; do not claim unrestricted
full PI or signoff validation. PDN target review/candidate screening must retain
that description until physical optimization is actually qualified.

Absent from public source, docs, manifests, dependencies, tests, help, strings,
examples, screenshots, binaries and distributable history:

- EMI implementation, catalogs, placeholders and upgrade advertising.
- ODB import and other non-KiCad importer implementations/examples.
- SPICE/circuit workbench, circuit runtimes/models, transient solvers and their
  implementation dependencies that have no independent admitted use.
- Account/login, activation, entitlement, user/device licensing and mandatory
  online service interfaces, endpoints and supporting infrastructure.
- Prior private branding, including case/spelling variants of SigHarmonic,
  subject to lawful ownership correction described below.

Stage 1 must not bundle dormant SI or thermal implementations. Publish future
SI/thermal roadmap descriptions only if wanted; no inaccessible UI tabs are
required. Excluded capability implementations are removed, not feature-flagged.

Retain security controls: approved file paths, project integrity verification,
signature verification, resource limits, process containment and extension
permissions. Removing user authentication must not accidentally remove these.
Copyright/license notices remain available through About/legal resources;
removing the licensing interface means removing product activation/commerce UI.

Owner confirmed during planning: the same SPICE/transient exclusions apply to
the separate public solver project. SI time-domain tools
need their own scope decision before Stage 2 so they do not silently reintroduce
withheld circuit/transient implementations.

## 3. Existing evidence and discrepancies

| Observed evidence | Release implication |
| --- | --- |
| `ARCHITECTURE.md`: React/TypeScript, thin Rust host, Python services, numerical kernels, versioned design/spec/result boundaries | Preserve these boundaries; no UI rewrite or language expansion is needed |
| `git rev-parse --verify HEAD` fails; root files currently appear untracked | A fresh public history does not establish original ownership; recover upstream histories/records or document provenance per file |
| `LICENSE`, `LICENSING.md`: mixed licenses, earlier MIT grants, ownership gaps | No blanket relabeling or relicensing |
| `THIRD_PARTY_NOTICES.md`: expressly incomplete | Generate artifact-specific dependency and asset inventories |
| `docs/PI_RELEASE_QUALIFICATION.md` and `docs/SOLVER_STATUS.md`: internal gate blocked and capability limitations remain | Create a distinct public-scope gate by ADR; preserve accuracy thresholds and do not reinterpret the internal gate as passed |
| Readiness docs refer to older desktop versions while `tauri.conf.json` is 0.2.12 | Regenerate versioned readiness evidence for the actual immutable candidate |
| `app/src-tauri/tauri.conf.json`: whole Python/extension directories copied; broad physics description; preview/commercial license resources | Dedicated allowlisted packaging is necessary; current bundle is not a sanitized release |
| Windows `webviewInstallMode` is `downloadBootstrapper` | Qualify an offline runtime distribution strategy before claiming offline installation |
| `scripts/build_linux.sh` invokes generic Tauri build; current bundle targets are NSIS/MSI | Linux documentation is not proof of an AppImage; add explicit Linux configuration and actual clean-machine evidence |
| `python/spike_core/extensions.py` imports `si_protocol_suites` | Separate generic extension discovery from staged domain registrations |
| `docs/EXTENSION_ARCHITECTURE.md`: external packages catalogued but normal desktop execution blocked; process separation not a complete sandbox | Preserve trust boundaries and accurately document developer/bundled execution; unrestricted public plugin execution is additional work |
| `docs/adr/0018-portable-results-and-board-visuals.md`: v3 projects and standalone v2 results | Use actual schemas and fixtures as compatibility authority; older project documentation contains legacy descriptions |
| Marble assets already have pinned source/hash/capture records | Reuse eligible assets after matching them to the public UI; current report capture says analysis was not run |
| `docs/SOLVER_REFERENCES.md` and generated research inventory exist | Curate real method lineage; do not invent acknowledgements or import unrelated private-domain references |
| Public governance files such as root SECURITY, CODE_OF_CONDUCT, GOVERNANCE and MAINTAINERS are absent | Add actual public reporting channels and decision authority; an internal security design document is not a disclosure policy |
| `kicad_plugin/metadata.json` declares MIT and a placeholder repository URL | If this integration ships, correct metadata against its verified license boundary and real public repository |

There are multiple things currently called SPIKES: the in-tree circuit engine
and standalone copies, and `D:\PROJECTS-DEV\SPIKES`, a separately developed
native multiphysics project. The latter's LICENSE is currently proprietary;
SPIKE's status document treats its PCB adapter as discovery/verification-only.
Do not copy either whole project or substitute it for working PI solvers based
on its name. Determine the exact eligible DC/AC kernel and helper ownership
closure at freeze. The public solver project must contain everything needed
to build and execute its declared capabilities without private components.

## 4. Licensing and ownership proposal

The following are proposed destinations, not changes to existing grants:

The owner's stated priority is easier commercialization while preserving an
open-source offering. Recommend the Apache UI/SDK plus MPL solver combination
below. Apache for every owned component is even simpler for unrestricted reuse,
but would not require recipients to share distributed solver modifications.
GPL plus commercial dual licensing is the alternative for stronger leverage
over proprietary reuse, not the simplest operational path. No license selection
has been applied to source files by this plan.

| Material | Proposed policy | Commercial consequence |
| --- | --- | --- |
| Owned desktop UI, shell and application integration | Apache-2.0 | Enables proprietary UI development and OEM use; competitors get the same reuse rights |
| Owned standalone numerical solver implementation | MPL-2.0 | Distributed changes to covered files remain available under MPL; separate proprietary UI files can coexist |
| Owned SDK, protocol schemas and minimal samples | Apache-2.0; retain existing MIT where applicable | Low-friction commercial and community extensions |
| Previously licensed or third-party code | Preserve applicable original terms and notices | Compatibility audit governs redistribution and combinations |
| Owned prose and illustrations | CC-BY-4.0 proposal with explicit scope | Reuse with attribution; board-derived assets retain applicable upstream terms |
| Third-party boards, photos, fonts, icons and models | Exact upstream licenses, per asset | No blanket documentation license overrides them |
| Project name/logo | Separate truthful trademark policy | Protect identity/endorsement without restricting licensed code use |

Apache permits commercial redistribution and grants specified patent rights;
it does not reserve commercial UI use to the original author. MPL has file-level
source-sharing obligations on distribution. This combination favors adoption
and proprietary integration, rather than charging for permission to do what
the public licenses already allow. See the [Apache license](https://www.apache.org/licenses/LICENSE-2.0)
and [MPL FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/).

Alternative if reciprocal UI forks and commercial relicensing revenue are the
priority: evaluate GPL-3.0-or-later UI plus a separately negotiated commercial
license, with contributor grants sufficient for both. GPL permits sales and
commercial use; it is not a commercial-use ban. Dual licensing requires rights
over all relevant contributions. See the [GNU licensing FAQ](https://www.gnu.org/licenses/gpl-faq.en.html).
AGPL is a separate option where network deployment obligations are actually
desired; it is not needed merely to sell a desktop UI.

Keep DCO sign-off for provenance. If proprietary relicensing of reciprocal
contributions is desired, adopt a clear, reviewed CLA before accepting them;
DCO alone is not an assignment or a general relicensing grant. Contributions
under permissive terms already provide broad reuse rights, subject to their
conditions. Explain any CLA openly and credit contributors. See the
[Developer Certificate of Origin](https://developercertificate.org/).

Use `Copyright (c) <actual years> Yawar Badri` for all verified owner-authored
material in both projects. Yawar Badri is also the named maintainer; `wayri`
is solely the GitHub username, never a copyright-holder name. Preserve accurate creation years and
other authors' notices. If SigHarmonic was only an erroneous label, record the
correction privately. If an entity actually owns rights, obtain the necessary
assignment/permission and lawful notice treatment before public reattribution.
If required notices conflict with zero-brand-trace requirements, replace or
exclude the affected material until resolved; do not erase ownership evidence.

Previously granted open-source rights cannot simply be withdrawn from existing
recipients. Open source also permits commercial use by others; noncommercial
restrictions are not an open-source solution. See the
[Open Source Definition](https://opensource.org/osd). Resolve ownership and
license compatibility with qualified review before the first public grant.
Process separation is a useful engineering boundary, not an automatic exemption
from copyleft or redistribution obligations.

## 5. Release workspace and source flow

Planned location after the internal freeze:

```text
D:\PROJECTS-DEV\open-source-release-output\
  internal-release-control\       private plan, exclusion rules, provenance map
  spike\                          independent public Git repository
  spike-solvers\                  independent public Git repository
  builds\                         disposable, untracked build directories
  candidates\<version>-rc.<n>\    immutable outputs plus evidence
  releases\<version>\            promoted, immutable outputs
```

Do not initialize the umbrella directory as a public repository. Each project
gets its own Git history; generated builds and private control records stay
outside those repositories. The intended public names are provisional.

After freezing and identifying the internal source snapshot, create a reviewed
positive file/dependency allowlist and deterministic export into a fresh tree.
Do not clone private history, mirror the workspace, or rely on `.gitignore` to
sanitize it. Record internal origin hashes privately; public manifests describe
only admitted contents and verified third-party origins.

Inspect the full dependency closure and generated content. Split mixed files
along existing contracts where necessary. Rebuild entirely from exported source
in an isolated environment; never reuse internal `dist`, Python bytecode,
native binaries, wheels or solver bundles. Check Python frozen archives,
JavaScript chunks/source maps, resources, binaries/debug metadata and nested
archives as well as filenames and source text.

Run secret, personal-path, branding and withheld-content checks against both
exported source and unpacked artifacts. Keep the literal withheld-name rules
and private audit evidence outside public repositories. Public CI can enforce
an admitted-file inventory, approved API/capability surface and dependency
allowlist without publishing a private-feature blacklist. Resolve false
positives against retained security functions and mandatory upstream notices.

Owner privacy requirement: scrub previously copied machine-specific paths,
personal email/address details and workstation identifiers from source, docs,
examples, logs, fixtures, screenshots and public Git metadata. Examples use
generic project paths. Use the verified GitHub noreply commit email, never a
personal contact address. Retain the agreed legal copyright and GitHub identity.
No screenshots enter the export without visual review; no debug symbols or
compiler/source paths enter published artifacts without path-remapping review.
Existing private planning records remain outside public history.

After publication, public fixes enter the public repository first where
practical and are imported internally by reviewed commits. Private features
enter public source only by explicit staged exports/PRs. Do not repeatedly
overwrite the public repository with a new sanitized snapshot and lose
community contributions or release ancestry.

## 6. Architecture and extension contracts

Preserve the existing dependency direction:

```text
KiCad adapter -> DesignIR -> application orchestration -> solver API/process
                                                        |
UI / reports / exporters <- AnalysisResult <-------------+
```

The standalone solver owns numerical methods, numerical helpers, units,
formulations and its independent tests. It must not import UI, KiCad parsers,
account services, or desktop preferences. The desktop owns board ingestion,
interaction and result presentation. Use versioned normalized data and a
bounded process protocol at the application/solver boundary; expose a stable
C ABI only where already justified. Define one owner for shared schema sources
and publish/pin their versions rather than maintaining divergent copies.

Use independent desktop and solver versions plus a tested compatibility matrix.
Negotiate protocol versions and capabilities before execution. Unsupported
contracts fail visibly; no implicit fallback or result-state promotion. Pin the
tested solver in desktop artifacts and support explicit upgrades only after
compatibility qualification. A clean source build must have a working public
baseline; optional accelerators cannot be hidden mandatory dependencies.

Build release-specific registration modules for importers, workflows, result
renderers and extensions. Do not scatter stage checks through domain code or
package dormant private modules. Remove cross-domain eager imports and ensure
stage selection actually determines compiled/packaged dependency closure.

Extension documentation must include:

- A minimal end-to-end PI result exporter or report extension, with no private
  imports, plus reference manifest/request/result files.
- Extension-point ownership, supported API versions, capability negotiation,
  schemas, errors, units and validity/provenance rules.
- Local authoring, build, test, packaging, discovery, installation, explicit
  user trust, upgrade, removal and troubleshooting workflows.
- Permissions, path boundaries, timeout/cancellation/resource limits, minimal
  environments, network policy and the limits of process isolation.
- Separate declarative/schema-driven panels from executable extensions; never
  inject arbitrary third-party JavaScript into privileged Tauri UI.
- Hash/signature and publisher policy if external execution is enabled; do not
  pretend current discovery-only packages are generally executable.
- Windows/Linux examples, conformance tests, compatibility/deprecation policy,
  licensing guidance for proprietary extensions, and SDK version pinning.

A process-isolated plugin is still executable code. Scope the first SDK to the
trust model actually implemented; public marketplace execution is a separate
security milestone. Keep extensibility generic without bundling withheld
importers or engines. Third-party development under an open license cannot be
universally forbidden merely because the official distribution omits a feature.

## 7. Preventing regressions across stages

Freeze the admitted PI project/result/export corpus before removing features.
Preserve `.spike` v3 ZIP64 project semantics, admitted legacy reader paths,
`AnalysisResult`, standalone `spike/result-package/v2`, and applicable existing
CSV/JSON/report/image exports as established by an actual export inventory.
Do not advertise a format based solely on this plan. Preserve units, precision,
IDs, source geometry association, warnings, solver provenance and model status.

Avoid schema renumbering for a marketing release. New domain data uses
versioned additive structures. Required new semantics set a minimum reader;
older readers must not silently discard or misinterpret them. Unknown optional
data may remain opaque where bounded and safe; unsupported required features
must be rejected without overwriting the original. Do not keep excluded-domain
decoders solely for private-project compatibility. Guaranteed compatibility
covers admitted public PI projects/results, not every internal project.

Each release must prove:

1. Earlier public projects/results open and retain their numerical data,
   visualization identity and supported exports; round trips do not drop data.
2. Numerical regressions meet independently justified tolerances, conservation
   checks and convergence criteria. Changed models have explicit baselines and
   migration/release notes; performance improvements cannot mask accuracy loss.
3. Original public SDK examples still run on compatible API versions; invalid
   manifests, bad outputs and incompatible engine versions fail safely.
4. New SI or thermal registration does not change PI defaults or interpretation.
5. Source and packaged workers report the same supported capabilities and
   produce equivalent fixture results on supported Windows/Linux platforms.
6. Save/load, crash recovery, cancellation, large inputs and low-resource errors
   remain safe; no network access is required for normal admitted workflows.

Use a separate public PI qualification contract with an explicit scope and
unchanged rigor for retained workflows. Unvalidated in-scope PI work blocks a
qualified release; it is not made validated by removing the old circuit gate.
If only an experimental preview is ready, name and document it as such rather
than calling Stage 1 complete. Exact numeric gates are written and reviewed
before running acceptance, including knowledgeable human review of numerics.

## 8. Repository directives and contributor material

Root `AGENTS.md` should be concise and link canonical human-readable guidance:
repository boundaries, build/test commands, license/provenance rules, contract
compatibility, numerical-review requirements, security-sensitive paths,
preservation of other changes, and evidence-based completion. It must not
require a particular paid AI service or contain private product plans.

Add narrowly scoped directives only where requirements differ:

| Location | Specific obligations |
| --- | --- |
| UI directory | Presentation-only physics; accessible states; no invented results; offline UI; supported workflow regressions |
| Rust host | Thin host; approved paths; bounded IPC/processes; no solver logic |
| Application/import services | KiCad adapter isolation; units/IDs; capability honesty; compatible schemas |
| Solver repository | Governing equations; derivation; conditioning/convergence; numerical oracles; performance bounds; human numerical review |
| SDK/extensions | Versioning; permissions; conformance; no private imports |
| Packaging/CI | Clean public-only builds; artifact inventory; secrets/signing boundaries; platform/offline qualification |
| Docs/examples/assets | Exact released UI; verified asset rights; reproducible result provenance; accurate capability claims |

Ship in EACH public repository as applicable: `README.md`, actual `LICENSE`
texts and `LICENSES/`, SPDX/REUSE mapping, `CONTRIBUTING.md`, DCO/CLA policy,
`CODE_OF_CONDUCT.md`, `SECURITY.md` with a real contact channel,
`GOVERNANCE.md`, `MAINTAINERS.md`, `CODEOWNERS`, issue/PR templates,
`ARCHITECTURE.md`, `DEVELOPMENT.md`, `TESTING.md`, support policy,
`CHANGELOG.md`, release procedure, compatibility/deprecation policy,
`THIRD_PARTY_NOTICES.md`, `ACKNOWLEDGEMENTS.md`, `CITATION.cff`, research
references, benchmark/validation guide, known limitations and example licenses.
Provide an extension guide and API reference with runnable examples. Add
`FUNDING.yml` only for verified funding destinations. AGENTS directives never
replace contributor instructions or executable CI checks.

## 9. Acknowledgements and public assets

Maintain three distinct records: legal notices for incorporated dependencies
and assets; acknowledgements for contributors/inherited work; research method
citations linked to implementations and validation. A citation does not supply
code redistribution permission or prove independent implementation. Do not claim
clean-room authorship for inherited code; preserve its actual origin and rights.

Curate the existing research ledger for admitted methods, including the recorded
Ruehli PEEC and Rosa/Grover inductance references where those implementations
ship. Record DOI/URL, bibliographic metadata, method used, affected module,
independent derivation/test oracle, validity limits and unresolved provenance.
Generate actual dependency notices from the released lockfiles and binaries
(including applicable Python, NumPy/SciPy, Eigen/nanobind, React, Three.js,
Tauri and transitive components), rather than assuming every installed tool is
a shipped dependency. Excluded tooling belongs only in the private audit.

Prefer pinned Marble KiCad sources and newly captured public-candidate UI.
The upstream [Marble repository](https://github.com/BerkeleyLab/Marble)
declares CERN OHL v1.2; the existing asset register also records its copyright
and U.S. Government rights notice. Verify each board/image/model separately;
"CERN board" is not itself a license grant. Preserve notices and exact source
revision, mark modifications, and avoid implying institutional endorsement.

Each distributed asset needs path, hash, source URL/commit, author/owner,
license, redistribution evidence, modifications and required credit. Include
board sources or corresponding source information where required, plus rights
for associated 3D models/fonts. Never reuse private/customer board captures.
Record final binary digest, board revision, setup, solver version and result
file for PI visualization screenshots. Show units and model-status limits;
existing "ANALYSIS NOT RUN" captures are not evidence of computed PI results.

## 10. Packaging and immutable candidates

Owner decision: retain the original SPI logo and existing application icon
assets without alteration. All generated concepts under `branding/` are rejected
release alternatives and must not enter either release repository. Preserve
the existing native PNG/ICO, web icon and favicon hashes during export. Use the
original branding for release captures and packaging; an icon redesign is no
longer part of the release scope.

Provisional targets: Windows x64 portable ZIP, Windows x64 installer EXE, and
Linux x86_64 AppImage. Choose MSI only if there is a concrete additional need;
it need not become a fourth promised artifact. Confirm minimum OS versions
through actual qualification before publishing support claims.

All artifacts carry the same public feature inventory and a packaged local
worker, required numerical/native dependencies, legal notices and version
metadata. End users must not need developer Python, Node, Rust or compilers.
Any KiCad CLI or 3D library requirement must be explicit; qualify the intended
board import path on a clean machine and bundle only redistributable pieces.

For Windows installer, evaluate WebView2 `offlineInstaller`; for an actually
no-admin portable ZIP, evaluate a redistributable fixed runtime and its update
policy. Do not assume an installer bootstrapper makes a ZIP portable. Tauri's
[Windows installer documentation](https://v2.tauri.app/distribute/windows-installer/)
describes these choices. WebView2 itself has Microsoft redistribution terms;
an open-source application does not make every platform runtime open source.

For AppImage, build against the oldest declared compatible platform and test
WebKitGTK, graphics, bundled worker/shared libraries, FUSE and extraction
fallback on the supported systems. AppImage does not mean arbitrary Linux
compatibility; see [AppImage concepts](https://docs.appimage.org/introduction/concepts.html).

Qualify extraction/first launch, blocked-network startup and full PI workflow,
non-admin operation, Unicode/space paths, save/export/reopen, cancellation,
upgrade and uninstall (installer), portable state and side-by-side versions,
and safe rollback. Uninstall must preserve user projects. Test without source
checkout access or developer environment variables.

Each RC gets immutable source commit IDs, dependency lock hashes, exact
toolchain versions, SBOMs, license/asset inventory, checksums, build provenance,
signatures, source archive(s), corresponding-source materials where required,
test reports, numerical qualification evidence and clean-machine records.
Sign Windows executables/installers with the selected verified publisher
identity. Restrict signing to reviewed release jobs; untrusted PRs never gain
release secrets. Publish only an artifact whose exact digest passed the gate.
A changed binary is a new candidate and requires affected checks again.

## 11. GitHub versus GitLab

Position both projects independently of any PCB source format. The SPIKE
repository description should be: "Offline PCB integrity workbench with
interactive visualization, portable results, reporting, and extensible analysis
workflows." The solver repository description should be: "Independent numerical
solver suite for PCB integrity analysis, with versioned interfaces, reproducible
benchmarks, and validation evidence."

Keep current capabilities explicit in the README and release notes: the initial
release supports KiCad board import and the admitted PI scope. This describes
current support without defining the project as permanently KiCad-only. Broad
positioning does not imply that other importers or physics are shipped. Do not
mention withheld importers in public descriptions or roadmaps.

Recommend GitHub as the public home, provisionally `wayri/spike` and
`wayri/spike-solvers`, with one primary issue tracker and release authority.
This is a fit judgment for a developer-facing community project, not a claim
of guaranteed adoption. Public standard Windows/Linux GitHub-hosted Actions
runners are currently free; larger runners/storage have separate constraints.
See [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
[GitHub Sponsors](https://docs.github.com/en/sponsors/getting-started-with-github-sponsors/about-github-sponsors)
is a possible funding channel, subject to account and regional eligibility.

GitLab is reasonable when self-managed infrastructure/control or an existing
GitLab team workflow is decisive. Its qualifying open-source program currently
offers Ultimate and compute credits/minutes, with namespace visibility/license
requirements; do not presume private commercial projects qualify in the same
namespace. See [GitLab community programs](https://docs.gitlab.com/subscriptions/community_programs/).
Avoid two writable public origins initially. An optional read-only mirror can
be added after release without splitting issues or signing authority.

## 12. Execution milestones after the internal freeze

| Milestone | Deliverable | Acceptance evidence |
| --- | --- | --- |
| M0: scope and rights | Frozen source identity, PI feature inventory, selected solver source, license/ownership decisions | No unresolved ownership for exported files; retained feature qualification criteria reviewed |
| M1: release extraction | Two buildable public source trees and private export controls | No withheld code/traces in admitted closure; public-only clean builds; complete required source |
| M2: compatibility and SDK | Separated domain registration, stable public contracts, extension examples and policy | PI golden corpus, migration/export tests, SDK conformance and failure tests |
| M3: governance and examples | Full contributor/directive/legal material, curated research credits, public-board captures | Notice/asset review, links verified, examples reproduced with exact release build |
| M4: candidates | Three desktop artifacts and separately versioned solver source/binary deliverables | Offline clean-machine, source/package parity, security, numerical and compatibility gates |
| M5: publication | Reviewed public repositories and immutable tagged assets | Complete evidence attached to exact digests; maintainer release decision |
| M6: SI, then thermal | Additive releases on the same public history | All prior-domain gates plus new-domain qualification and compatibility evidence |

Do not promise a date before M0/M1 expose the true dependency-removal and
validation work. Both projects' circuit/transient exclusions are confirmed;
the exact eligible standalone solver source and final license grant still need
rights-based review. Platform baseline and publisher identity can be settled
during packaging preparation. No release copy, Git repository, binary build,
copyright replacement or publication was performed by this planning task.
