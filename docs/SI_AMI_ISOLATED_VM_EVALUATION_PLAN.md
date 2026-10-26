<!-- SPDX-License-Identifier: Apache-2.0 -->
# Isolated-VM AMI evaluation plan

Prepared 23 October 2026 at the owner's request. **Plan only**: no VM was
created, operating-system feature enabled, installer/model launched, agreement
accepted, account used or spending incurred. Approval to prepare this plan is
not approval to execute it or to accept an unknown license.

## Objective and exact candidate

Discover TI's exact package terms and Windows model members without executing
the unsigned installer on the engineering workstation. Only after separate
rights/trust review, test bounded interoperability through SPIKE's unchanged
Windows x64 AMI development API **inside the disposable VM**.

The [public admission record](validation/AMI_PUBLIC_ADMISSION_20261023.md)
identifies the official TI SPRM731 ZIP, 45,541,410 bytes, SHA-256
`33b8850262fac8702ad094a16b5897b91d3c672512a67497894e0630153a09e3`.
Its sole installer is `SPRM731-1.0-windows-x64-installer.exe`, 47,699,449 bytes,
SHA-256 `22bbddd578e0cf955bf87ad64e5ffa444a60f983d09d2c8474f34fdb0ff09903`.
It is unsigned. Static inspection found TI product metadata but no supported
container reader could expose the exact inner Windows models and terms.
Official download origin plus hashes identify acquired bytes; neither proves
that arbitrary native code is safe or licensed for the proposed use.

## Stage 0 — approve and verify the isolation environment

Use an owner-approved disposable Windows x64 VM on an existing licensed,
patched hypervisor and guest. Hypervisor installation, OS acquisition,
license acceptance or cloud resources need separate approval if not already
available. Proposed caps are 4 virtual CPUs, 8 GiB guest memory, 40 GiB disk and
a one-hour inspection window; these are planning budgets, not measured needs.

Before admitting the installer, record guest/hypervisor build identities and
verify the following with harmless authored canaries:

- No virtual NIC, NAT, bridged connection, DNS or network access. Disconnecting
  only the guest browser is insufficient.
- No host/repository/home directory mappings, shared clipboard, drive/USB,
  printer, smart-card, audio/video or enhanced-session resource redirection.
- No project credentials, Git tokens, signing keys, personal accounts, software
  license secrets or confidential board data in the guest.
- A clean powered-off baseline and disposable writable guest disk/checkpoint.
  A checkpoint supports rollback; it is not itself an isolation guarantee.
- Read-only input media containing only the hash-pinned installer and necessary
  reviewed SPIKE test/runtime artifacts. No automatically executed logon command.
  Verify hashes inside the guest again.
- Local guest account, no host/domain identity. Any elevation is confined to
  this VM and requires the separately approved installation step.

Prefer a full disposable VM with explicit media/egress control, not default
Windows Sandbox settings. Microsoft's [Sandbox configuration reference](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file)
documents configurable network, clipboard and folder-sharing controls; these
must not be assumed disabled. Its [VMConnect resource reference](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/use-local-resources-virtual-machine-connection)
also identifies host resources exposed by enhanced sessions. Review those
controls on the exact chosen build. This plan does not certify containment
against hypervisor vulnerabilities or make SPIKE's Job Object a sandbox.

If the chosen environment cannot enforce and demonstrate this boundary, stop.
Do not fall back to launching on the host. Stage 0 acceptance requires the
owner's approval of the named VM/environment and permission for Stage 1.

## Stage 1 — installer terms discovery, no assent

Launching the installer executes untrusted code even before an agreement page
appears; therefore this step occurs only after Stage 0 approval. Observe it
through the VM console, with external time limits enforced by the VM operator.
Do not use unattended, silent, accept-license or automatic-next switches.

Capture the installer title, exact displayed terms/version, all named linked
terms, publisher claims and requested dependencies/privileges. Preserve the
complete license text as data if the installer exposes it before assent;
otherwise retain complete console screenshots, not a partial paraphrase.
Keep SHA-256 identities and an operator action log. Do not enter personal
details or grant download/network access. No box asserting agreement is checked.

Stop at the first consent, install, dependency, login, privilege or network
decision. If terms cannot be displayed without first accepting or installing,
report that fact and stop. Stop also on unexpected host interaction, resource
overrun or a changed input hash. Power down and quarantine the guest disk.
Evidence describing the exact terms goes to the owner/legal reviewer; unknown
terms are never treated as accepted by a broad development instruction.

## Stage 2 — separately approved guest installation and inert admission

Requires explicit owner review/acceptance of the exact terms for internal
evaluation in a third-party host, plus approval of any required dependencies.
No redistribution approval is inferred. If the terms or dependency conditions
do not permit this use, stop and seek an appropriate vendor package instead.

Install only inside the isolated guest, recording actions and file changes.
No Internet access is added to satisfy an installer requirement. Inventory the
exact `.dll`, `.ami`, `.ibs`, package/readme and license files; retain matched
revision, byte sizes, hashes, declared valid conditions and correspondence.
Do not inspect, adapt or copy vendor implementation/source code.

Apply the existing [AMI admission contract](SI_AMI_EXECUTION.md) before loading:
AMD64 PE64 kind, exact model/host hashes, at most 32 MiB model, matching supported
parameter semantics, no unsupported delay imports or dependencies. The current
admitted CRT/System32 import set remains unchanged. A bundled runtime or missing
dependency does not justify copying DLLs into System32 or relaxing the gate.
Unknown parameters are not deleted and legacy models are not relabeled.
An unsupported result is an admission failure, not an interoperability run.

## Stage 3 — approved bounded model execution inside the VM

Requires a second explicit decision that the model/license/dependency review
permits execution under SPIKE's trusted-development boundary. Execute only the
existing API and host in the VM, with Windows Job Object memory, wall-time,
one-process, cancellation and kill-on-close limits intact. No generic worker,
UI or project file may implicitly trigger a model load.

Derive requests from the exact vendor documentation and retained parameter
definitions: direction, supported mode/rate/corner, seconds-valued sample and
symbol times, physical impulse normalization and voltage interpretation.
Do not invent defaults for unavailable declarations or claim that AM64x models
represent Marble's Kintex-7 or WREN's Zynq UltraScale+ FPGA devices.

Record input/model/host/parameter hashes and full bounded result/error evidence.
Verify Init/GetWave/Close lifecycle, return codes, output grammar/finiteness,
state continuity under allowed block partitions and clock rules where applicable.
Distinguish repeatability/ABI evidence from independently specified numerical
accuracy. Compare output only against vendor/reference results with matching
stimuli, units and published applicability/tolerances. If such results are not
available, report their absence: a finite waveform or attractive eye is not a
reference comparison. No BER, CDR lock, training, protocol or board compliance
is inferred from successful ABI calls.

## Evidence egress and completion

No writable host folder or clipboard is enabled for convenience. Power down
the execution VM; treat its disks and all produced files as untrusted. An
approved second disposable inspection environment must enforce the same Stage 0
network/resource restrictions. Its export allowlist is validated UTF-8 plain
text and canonical JSON (at most 8 MiB each), plus decoded and freshly
re-encoded PNG console images (at most 16 megapixels and 8 MiB each). Reject
HTML, scripts, office/PDF documents, executables, source archives, traversal,
symlinks, misleading extensions and unexpected members; a regular file alone
is not passive. Apply a 64 MiB aggregate export cap. Do not automount or auto-open the compromised
guest volume on the engineering workstation. Host transfer of model binaries
requires a separate trust/rights decision; guest execution does not authorize it.

Retain the input and approved license identities, environment/isolation checks,
consent boundaries, operator log, admission decisions, exact requests, observed
results and independent comparison status in a fresh evidence directory.
No vendor models/licenses are put in Git or the installer by default. Dispose
of only the explicitly named evaluation VM after approved evidence retention;
preserve the original downloaded inputs and failure records.

Completion of this plan means a reviewed, executable evaluation procedure.
Completion of a future run means only the exact demonstrated interoperability
scope. Production/vendor physical validation and Marble/WREN SERDES/10GbE
qualification require their own models, networks, standards and correlation.
