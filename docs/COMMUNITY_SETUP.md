# SPIKE Community and Repository Governance Setup

Selected policy: use the existing `SPIKE-Multiphysics simulation suite`
Discord server and the solo-maintainer GitHub PR policy with zero mandatory
external approvals.

## Applied state (2026-10-18)

- Public welcome-channel invite: [Join SPIKE](https://discord.gg/EvGh3cXtk).
  Discord reports a 30-day expiration and unlimited uses. A permanent invite
  remains pending owner approval; do not imply this link never expires.

- GitHub's public repository description and Discord's saved server description
  now use the PCB-focused, board-to-complete-assembly positioning. The welcome
  topic carries the same scope and retains the existing community rules.
  Large-scale coupled simulation is explicitly a roadmap objective.

- Server icon: the existing 512 x 512 SPIKE S mark from
  `app/public/spike-icon.png` was uploaded, saved and verified in the server
  sidebar. The full wordmark was replaced with the compact mark.

- Existing server: [SPIKE-Multiphysics simulation suite](https://discord.com/channels/1560191329269719081/1560191331249160235).
- Discord category `START HERE` and text channel `welcome-and-rules`
  (`1561332852488937593`) were created. Its persisted topic describes the
  broader multiphysics scope with PCB and KiCad capabilities, links GitHub, and
  asks members to be respectful; state versions, units, and model limits;
  protect private data; and route reproducible bugs to GitHub.
- `welcome-and-rules` is read-only for `@everyone`: `Send Messages`, `Send
  Messages in Threads`, `Create Public Threads`, and `Create Private Threads`
  are denied. `View Channel` remains unchanged and inherits its existing
  category/server setting. The saved overrides were verified in the permission
  editor.
- Discord category `ENGINEERING & PROJECT` was created with two Forum channels:
  - `engineering` (`1561336001467650138`) asks for one question or study per
    post, with version and workflow, assumptions, materials, units, boundary
    conditions, mesh or convergence evidence, expected and actual behavior,
    explicit model limits, and public data. Reproducible defects route to
    GitHub Issues. Verified tags: `PI`, `SI`, `Thermal`, `EM-RF`, `Circuits`,
    `Coupled studies`, `Geometry-Mesh`, and `Validation`.
  - `contributing` (`1561337282726994072`) routes changes through GitHub issues
    and pull requests and links `CONTRIBUTING.md`. Its guidelines ask for scope,
    affected workspaces, acceptance checks, DCO sign-off, licensing, required
    knowledgeable human numerical review before release, and protection of
    private data. Verified tags: `Getting started`, `Documentation`, `Feature
    proposal`, and `Validation`.
- Existing text channels `general`, `updates`, `bugs`, `help`, and `show-case`,
  and the existing `General` voice channel, were preserved. No messages were
  posted. The public invite is recorded above; no role, bot, token, or administrator grant was created.
- Optional AutoMod, Onboarding, moderator roles, and the remaining channel plan
  below were not configured and remain proposals.
- GitHub ruleset `25144029` is now **Protect main**, active on the default
  branch, with PRs, resolved conversations, zero required approvals, linear
  history, deletion protection, force-push protection, and no bypass actors.
- CI is **not yet required**. The workflow trigger repair is local and must be
  merged and pass before adding the `checks` requirement. No release or source
  branch was published as part of the protection update.

The following Discord structure is the implementation plan; channel and role
settings are only applied where separately recorded.

## Project positioning

Use this short description consistently:

> PCB-focused multiphysics, from board to complete assembly.

Use this longer description where the distinction between workflows matters:

> SPIKE is an open-source, local-first multiphysics workbench centered on PCBs
> and the systems built around them: boards, circuits, interconnects, enclosures
> and mechanical parts. Prepare supported electrical, thermal, airflow, EM/RF
> and mechanical studies in shared assembly context. Large-scale coordinated
> simulation is the product direction; present coupling, geometry coverage and
> execution limits remain workflow specific.

Saved Discord server description:

> PCB-focused multiphysics, from board to complete assembly. Build, connect and
> study boards, circuits and mechanical systems with thermal, electrical and
> EM/RF workflows. Developing toward large-scale coupled simulation, with
> explicit solver limits and validation evidence.

See [product scope and assembly direction](PRODUCT_SCOPE.md) for the complete
positioning and the distinction between current foundations and scale targets.

Do not describe SPIKE as a generally validated multiphysics solver, a universal
full-wave or CFD tool, or a replacement for independent engineering review.
The repository's [solver status](SOLVER_STATUS.md) remains the authority for
validated, approximate, experimental, and unsupported capabilities. A UI,
adapter, example, or passing software test does not by itself qualify physics.

## Discord launch plan

### Ownership and launch boundary

The repository owner should create the server with an account protected by
multi-factor authentication. Start without third-party bots. Discord Community
mode supplies Rules Screening, Onboarding, Forum channels, AutoMod, and safety
controls without another service holding server permissions.

Before publishing an invite:

1. Enable Community mode and assign the rules channel and a private moderator
   updates channel.
2. Configure Rules Screening, Verification Level, AutoMod, the channel
   permissions below, and an invite that does not expire unexpectedly.
3. Test Onboarding with Discord's Preview function and with a non-privileged
   test account.
4. Seed `help-and-support`, `engineering`, and `showcase` with one example post
   each so members can see the expected format.
5. Publish the invite only after there is a named human who can check the
   moderation queue. Do not promise response times.

### Minimal channel structure

Use Forum channels for long-lived technical topics and text channels for
conversation. This avoids a separate mostly empty channel for every solver.

| Category | Channel | Type | Default | Purpose and posting policy |
| --- | --- | --- | --- | --- |
| Start here | `welcome-and-rules` | read-only resource | yes | Project scope, rules, privacy warning, GitHub and documentation links. |
| Start here | `announcements` | read-only announcement | yes | Releases, security notices, and material project changes. |
| Community | `general` | text | yes | Short project conversation; 5-second slow mode at launch. |
| Community | `introductions` | text | yes | Member background, interests, and permitted public projects. |
| Community | `showcase` | forum | yes | Screenshots, public examples, comparisons, and lessons learned. |
| Engineering | `help-and-support` | forum | yes | Reproducible questions and troubleshooting. Not an issue tracker. |
| Engineering | `engineering` | forum | yes | Model, numerical, validation, and workflow discussion. |
| Project | `contributing` | forum | yes | Contribution proposals and contributor help; repository records remain authoritative. |
| Project | `ideas` | forum | optional | Early feature ideas; accepted scope is recorded in GitHub. |
| Moderation | `mod-log` | private text | no | AutoMod alerts and moderator actions. |
| Moderation | `mod-room` | private text | no | Triage and incident coordination. |

The eight default public channels satisfy Discord Onboarding's current minimum
of seven default channels and provide at least five where `@everyone` can send
messages. If Discord changes that requirement, use the smallest set its setup
screen accepts rather than creating filler channels.

### Forum configuration

Set a tag requirement on the technical forums and use list view.

`help-and-support` tags:

- `install-package`
- `import-geometry`
- `pi-power`
- `si-channels`
- `thermal`
- `em-rf`
- `circuits`
- `extensions-automation`
- `solved`

Post guideline:

> Search first. Include SPIKE version, operating system, input type, expected
> result, actual result, relevant logs, and the smallest shareable example.
> Remove credentials, private board data, and material you cannot redistribute.
> Confirm whether the behavior is reproducible before opening a GitHub issue.

`engineering` tags:

- `pi`
- `si`
- `thermal`
- `em-rf`
- `circuits`
- `multiphysics-coupling`
- `numerics-validation`
- `units-modeling`

Post guideline:

> Name the workflow, model, assumptions, units, evidence, and expected validity
> range. Link the applicable Solver Status section. Clearly label proposals,
> approximations, and unvalidated results.

`contributing` tags:

- `good-first-contribution`
- `development-setup`
- `documentation`
- `tests-fixtures`
- `design-proposal`
- `needs-maintainer`

Pin links to `CONTRIBUTING.md`, `ARCHITECTURE.md`, the subsystem index, licensing
files, and the GitHub issue tracker. Discord discussion is advisory; an issue,
pull request, ADR, or checked-in validation record carries the durable decision.

### Roles and permissions

Keep role names and authority small:

| Role | Assignment | Permissions |
| --- | --- | --- |
| Owner | one server owner | Full control; recovery and final escalation. |
| Maintainer | manually assigned | Manage channels/events, messages, threads, webhooks, and roles below itself. Avoid `Administrator` when narrower permissions work. |
| Moderator | manually assigned | View audit log, manage messages/threads, timeout, kick, ban, and moderate members; no server, integration, or high-role management. |
| Contributor | manually assigned after an accepted contribution | Display recognition only; no extra moderation or repository authority. |
| Member | all screened members | Read, post, create forum posts, use threads, and attach files in public channels. No mass mentions or invite management. |
| Release updates | self-selected | Mentionable only by Maintainer for release notifications. |

Use self-selected interest roles only for discovery: `PI`, `SI`, `Thermal`,
`EM-RF`, `Circuits`, and `Extensions-Automation`. Do not create access silos for
these domains. Disable `@everyone`, `@here`, and role mentions for ordinary
members. Keep Administrator, Manage Server, Manage Roles, Manage Webhooks, and
Mention Everyone away from bots and community roles.

### Onboarding and Server Guide

Make `welcome-and-rules`, `announcements`, `general`, `introductions`,
`showcase`, `help-and-support`, `engineering`, and `contributing` default
channels. Ask two short questions:

1. Required, multiple choice: **What brings you to SPIKE?**
   - Get help: highlight `help-and-support`.
   - Discuss engineering: highlight `engineering`.
   - Contribute: highlight `contributing`.
   - Share work: highlight `showcase`.
2. Optional, multiple choice: **Which areas interest you?**
   - PI, SI, Thermal, EM/RF, Circuits, Extensions/Automation: assign the matching
     interest role. These roles should not unlock otherwise hidden help.

Add the optional `Release updates` role in Channels & Roles after join. In
Server Guide, use this welcome text:

> Welcome to the SPIKE community. Start with a public example, state the exact
> workflow and version, and treat every numerical result according to its
> documented model status and limits.

Use these new-member tasks:

1. Read the scope, rules, and privacy warning.
2. Read Solver Status for the workflow you plan to use.
3. Search `help-and-support`, then post a reproducible question if needed.
4. Choose interest and release-notification roles.

### Rules and moderation

Publish these concise rules through Rules Screening:

1. Be respectful. Critique methods and evidence, not people.
2. State versions, assumptions, units, and model status for technical claims.
   Do not present experimental or approximate results as qualified engineering
   evidence.
3. Search before posting and keep one support problem per forum post. Move a
   reproducible defect or accepted feature request to GitHub.
4. Share only material you may publish. Remove secrets, personal information,
   customer data, proprietary board files, and restricted third-party assets.
5. No spam, harassment, impersonation, malware, unsafe instructions, or
   unsolicited promotion. Do not use direct messages to evade moderation.
6. Support is community effort without a response or correctness guarantee.
   Moderators may retag, move, lock, or remove content to keep the record useful.

Initial safety settings:

- Verification Level: `Low` for the public launch; raise to `High` during a
  raid or sustained abuse.
- Explicit media filter: scan media from all members.
- AutoMod: enable Discord's commonly flagged words and spam-content filters;
  block mention spam above five unique mentions; send all alerts to `mod-log`.
- Custom keywords: add only observed project-specific abuse or impersonation
  terms. Review false positives before blocking technical vocabulary.
- Forum slow mode: 30 seconds between new posts; use per-post slow mode only
  when a thread becomes difficult to moderate.
- Direct-message spam protection and raid alerts: enable where Discord makes
  them available.

Escalation order: remove or retag accidental off-topic content; warn for a first
minor violation; timeout repeated disruption; ban spam, malware, impersonation,
doxxing, or deliberate evasion. Record time, moderator, rule, action, duration,
and a message link in `mod-log`. Keep sensitive reports in `mod-room`. Provide a
single appeal route to the owner or Maintainer and have a different moderator
review an appeal when one is available.

Do not accept vulnerability details in a public Discord channel. Until the
repository publishes a dedicated security policy, direct reporters to GitHub's
private vulnerability reporting interface if enabled, or to the repository
owner through a private channel the owner has explicitly published.

## GitHub protection audit

Read-only GitHub API inspection on 2026-10-18 found:

- `wayri/SPIKE` is public, its default branch is `main`, and the inspecting
  account has administrator permission.
- `main` at `b26deed77f4284194c1168a07b35c58c73307dce` reports protected through
  repository ruleset `RA` (ID `25144029`). The legacy branch-protection API
  returns `404 Branch not protected`, which is expected when protection comes
  only from a ruleset.
- `RA` is active on `~DEFAULT_BRANCH`, has no bypass actors, and enables:
  restrict deletions, block non-fast-forward updates, restrict updates, and
  require linear history.
- The `restrict updates` rule allows updates only by bypass actors. Because the
  ruleset has no bypass actors and reports that the current administrator can
  never bypass, the present configuration effectively freezes `main` rather
  than providing a pull-request workflow.
- `RA` does not require a pull request, review, conversation resolution, or a
  status check.
- The actual source workflow is `Source checks`; its only job/check name is
  `checks`, reported by `github-actions`. Recent `main` runs of `checks` passed.
- `.github/workflows/ci.yml` currently skips `docs/**` and all `*.md` paths for
  pull requests. GitHub documents that a workflow skipped by path filtering
  leaves a required check pending and blocks merge. Therefore `checks` must not
  be made required until that trigger is repaired.
- Release publication is tag driven: `.github/workflows/release.yml` runs for
  `v*`. Release branches are ordinary `codex/release-*` working branches and
  are currently unprotected. Existing `v*` tags are also not protected by a
  tag ruleset.
- Squash, rebase, and merge commits are all allowed. Linear history makes merge
  commits unusable on `main`; squash or rebase remains available. Auto-merge and
  automatic branch deletion are off. Web commit sign-off is off even though
  `CONTRIBUTING.md` requires a DCO sign-off on every submitted commit.
- GitHub Issues is enabled and GitHub Discussions is disabled. Secret scanning,
  non-provider scanning, validity checks, push protection, and Dependabot
  security updates report disabled.

### Recommended main ruleset

Edit the existing `RA` ruleset instead of layering a legacy branch protection
rule on top. Rename it `Protect main`, keep it active and target
`~DEFAULT_BRANCH`, then set exactly:

| Rule | Setting |
| --- | --- |
| Restrict deletions | On |
| Block force pushes / non-fast-forward updates | On |
| Restrict updates | **Off** |
| Require linear history | On |
| Require a pull request before merging | On |
| Required approvals | `0` while there is only one maintainer |
| Dismiss stale approvals | Off |
| Require review from Code Owners | Off until there is another qualified reviewer |
| Require approval of most recent push | Off while there is only one maintainer |
| Require conversation resolution | On |
| Require status checks | Stage as described below |
| Require branch to be up to date | Off initially; turn on if concurrent merges become common |
| Merge queue | Off for the solo-maintainer stage |
| Bypass actors | None |

Zero required approvals still forces every update through a visible pull
request, while avoiding a solo-maintainer deadlock. Numerical release review is
a project requirement and cannot be manufactured by a self-approval setting;
record the knowledgeable human review in the pull request or validation record.
When a second active qualified maintainer exists, raise approvals to one for
source changes and require Code Owner review for numerical kernels and release
automation.

Apply in this order so `main` is not accidentally locked:

1. Prepare a pull request that makes `Source checks` run on every pull request.
   The minimal repair is to remove `paths-ignore` from the `pull_request` event.
   A later optimization may keep one always-created `checks` gate and skip only
   expensive steps for proven documentation-only changes.
2. Confirm a documentation-only test pull request and a source test pull
   request both report a successful `checks` check from GitHub Actions.
3. Edit `RA`: remove `restrict updates`, add the pull-request and conversation
   rules above, and require status check `checks` with source `GitHub Actions`.
4. Open a small pull request and verify direct push, force push, and deletion are
   rejected; the pull request can merge only after `checks` passes and all
   conversations are resolved.

Do not select `Source checks` as the required check name. GitHub rulesets use
the job/check name, which the API currently reports as `checks`.

Enable **Require contributors to sign off on web-based commits** in repository
settings. This covers commits created in GitHub's web interface. Add a dedicated
DCO check later if every command-line commit must be mechanically enforced;
cryptographic signed-commit protection is a different control and does not
satisfy the project's `Signed-off-by` requirement.

### Release protection

The current release mechanism publishes from immutable `v*` tags, so protect
the tags instead of all `codex/release-*` working branches.

Create a second active tag ruleset named `Protect release tags`:

| Setting | Value |
| --- | --- |
| Target | tags matching `refs/tags/v*` (UI pattern `v*`) |
| Restrict updates | On |
| Restrict deletions | On |
| Block force pushes / non-fast-forward updates | On if offered for tags |
| Restrict creations | On |
| Bypass | repository owner/administrator, `Always`, as the sole release actor |

This permits the owner to create a release tag while preventing collaborators
from creating, moving, or deleting a release tag. Treat the owner bypass as a
release credential: enable multi-factor authentication and do not grant it to
bots or general maintainers.

Before creating `vX.Y.Z`, require this manual release checklist:

1. The target commit is reachable from `main` and the intended release commit
   is recorded.
2. `checks` passed on that exact commit.
3. Version metadata and release notes agree with `vX.Y.Z`.
4. `python scripts/release_automation.py check` passes.
5. Required numerical human review and platform qualification evidence are
   linked; any held or experimental platform remains labeled as such.
6. Create the tag once. Never move or reuse a published version tag.
7. Confirm `Build and release SPIKE` completes its `preflight`, platform builds,
   `verify`, and `publish` jobs before announcing the release.

Do not protect all `codex/release-*` branches yet. They are working branches,
their names are not the publication boundary, and protecting them would add
maintenance without protecting a release. If a stable maintenance branch such
as `release/0.4` is introduced, give that explicit branch its own ruleset with
the same pull-request, `checks`, deletion, force-push, and linear-history rules
as `main`.

### Security settings to review before a broad invite

The API audit found GitHub security features disabled. Enabling public community
participation increases the value of these repository-native controls:

1. Enable secret scanning and push protection if offered for this repository.
2. Enable Dependabot security updates only with a maintainer willing to triage
   the resulting pull requests and verify lockfile changes.
3. Add a checked-in `SECURITY.md` that names the private reporting route and
   supported versions before soliciting vulnerability reports.
4. Keep GitHub Issues as the actionable defect record. Consider Discussions
   only if Discord knowledge is being lost and the maintainer can moderate a
   second public discussion surface.

These are recommendations, not verified applied settings.

## Acceptance checks

Community launch is ready when:

- a non-privileged account accepts Rules Screening, completes Onboarding, sees
  only intended channels, can post in all five interactive default channels,
  and cannot see `mod-log` or `mod-room`;
- forum tags are required and each technical forum contains a model post;
- AutoMod blocks a test mention-spam message and records the alert privately;
- the rules, support template, GitHub issue link, Solver Status link, and privacy
  warning work from a new-member account;
- `Protect main` passes the direct-push, force-push, deletion, docs-only pull
  request, source pull request, and unresolved-conversation tests;
- `Protect release tags` rejects an unauthorized create/update/delete attempt
  using a disposable test tag pattern before it is applied to production `v*`
  tags, or its ruleset evaluation confirms the intended actor behavior; and
- the final settings and test date are appended to this document without
  claiming tests that were not run.

## Official references

- [GitHub: About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
- [GitHub: Available rules for rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- [GitHub: Troubleshooting required status checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)
- [Discord: Enabling a Community server](https://support.discord.com/hc/en-us/articles/360047132851-Enabling-Your-Community-Server)
- [Discord: Community Onboarding](https://support.discord.com/hc/en-us/articles/11074987197975-Community-Onboarding-FAQ)
- [Discord: Server Guide](https://support.discord.com/hc/en-us/articles/13497665141655-Server-Guide-FAQ)
- [Discord: Forum channels](https://support.discord.com/hc/en-us/articles/6208479917079-Forum-Channels-FAQ)
- [Discord: AutoMod](https://support.discord.com/hc/en-us/articles/4421269296535-AutoMod-FAQ)
- [Discord: Raid protection](https://support.discord.com/hc/en-us/articles/10989121220631-How-to-Protect-Your-Server-from-Raids-101)
