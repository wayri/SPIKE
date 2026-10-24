<!-- SPDX-License-Identifier: Apache-2.0 -->
# AMI isolated-VM preflight (2026-10-23)

## Outcome

The owner subsequently authorized proceeding with isolated terms inspection,
then confirmed that no VMs are available. This authorizes the terms-discovery
purpose, not license assent or model execution. The operational blocker is the
missing verified isolation environment, not a lack of permission to inspect
terms once isolation is established.

A further read-only optional-feature/inventory query through the executor's
unsandboxed approval path still returned `The requested operation requires
elevation` for Hyper-V and Sandbox. No Hyper-V management module or `Get-VM`
command became available. Sandbox escalation did not provide Windows UAC
administrator elevation. No host setting was changed and no installer ran.

No existing environment could be identified that is ready for Stage 0 of
`docs/SI_AMI_ISOLATED_VM_EVALUATION_PLAN.md`. This was a bounded, read-only
inventory. No VM or sandbox was launched or created; no Windows feature was
enabled; no software was installed or downloaded; no agreement was accepted;
and neither the TI installer nor a model was executed.

The result is fail-closed. In particular, the mere existence of the protected
directory `C:\ProgramData\Microsoft\Windows\Hyper-V` is not evidence of an
available VM, usable Hyper-V installation, licensed guest, clean baseline, or
the isolation controls required by the plan.

## Host and inventory evidence

The host registry reports Windows client edition `CoreSingleLanguage`, display
version `26H2`, build `26300.9711`. The following checks were made without
elevation:

- `vmconnect.exe` and `WindowsSandbox.exe` were absent from their standard
  System32 locations. `WindowsSandbox.exe` was also absent from the checked
  Program Files location.
- VirtualBox `VBoxManage.exe`, VMware Workstation/Player `vmrun.exe`, and QEMU
  `qemu-system-x86_64.exe`/`qemu-img.exe` were absent from their standard
  Program Files locations.
- No Hyper-V, VirtualBox, VMware, QEMU, or Windows Sandbox product was found in
  the 32-bit or 64-bit machine uninstall registry inventories.
- None of the queried Hyper-V, Host Network Service, VirtualBox, or VMware
  services (`vmms`, `vmcompute`, `hns`, `VBoxSDS`, `VMAuthdService`,
  `VMUSBArbService`) was returned.
- The standard per-user VirtualBox and VMware VM directories and the checked
  public Hyper-V/VMware directories did not exist.
- `C:\ProgramData\Microsoft\Windows\Hyper-V` existed, but enumeration was
  denied. Windows optional-feature queries for `Microsoft-Hyper-V-All`,
  `Containers-DisposableClientVM`, and `VirtualMachinePlatform` also required
  elevation. Firmware/hypervisor CIM queries were unavailable to this client,
  and `systeminfo.exe` could not acquire its requested credentials. Therefore
  feature, firmware, and any protected machine inventory remain unknown, not
  disabled or absent.

The only eligible installer input remains inert at
`build/ami-public-admission-20261023/sprm731-static/SPRM731-1.0-windows-x64-installer.exe`.
It is 47,699,449 bytes and was re-hashed during this preflight as SHA-256
`22bbddd578e0cf955bf87ad64e5ffa444a60f983d09d2c8474f34fdb0ff09903`.

## Missing resources and evidence

Proceeding requires all of the following to be supplied or demonstrated before
launch, followed by explicit owner authorization for the named environment:

1. An existing licensed, patched hypervisor and an existing licensed Windows
   x64 guest, with their exact builds and management interface identified.
2. A named powered-off clean baseline and a disposable writable guest disk or
   checkpoint. The protected Hyper-V directory must not be treated as this
   evidence without an authorized inventory.
3. Configuration evidence that the VM has no virtual NIC, NAT, bridge, DNS, or
   other egress and that networking cannot be reintroduced automatically.
4. Configuration evidence disabling host folders/drives, clipboard, drag and
   drop, USB, printer, smart-card, audio/video, and enhanced-session resource
   redirection.
5. A local-only guest identity with no host/domain account or credentials, and
   a reviewed read-only-media procedure admitting only the hash-pinned input
   and necessary reviewed SPIKE artifacts.
6. Harmless guest/host canary checks that prove the network and resource
   boundaries before the installer is admitted.

Windows Sandbox is not an acceptable fallback on the current evidence: no
installed executable or feature state was established, and default settings do
not establish the required clipboard, mapped-folder, and network boundary.
Installing/enabling a hypervisor or Sandbox, creating a VM, acquiring an OS or
license, or using cloud resources is outside this authorization.

## Next decision

Stop before launch. A privileged operator may separately provide a read-only
feature/VM inventory or identify an existing licensed VM and its isolation
configuration. The owner must then approve that exact environment before any
Stage 0 canary launch. The current owner instruction authorizes Stage 1 terms
inspection conditional on the plan's isolation checks passing. It does not
authorize accepting terms, completing installation, enabling host features or
executing models. A suitable environment must first be provisioned or supplied
by an appropriately privileged operator; there is none available to this run.
