# Desktop update backend contract

The fixed source is the public stable release API at
`https://api.github.com/repos/wayri/spike/releases/latest`. No authentication,
repository override, caller download URL, installer path or arbitrary argument
is accepted by the renderer-facing native commands.

## Ownership and transport

`python/spike_core/app_updates.py` owns stable version comparison, exact Tauri
NSIS asset selection, HTTPS admission, bounded transfer and SHA-256 verification.
`app/src-tauri/src/app_updates.rs` owns main-window authorization, job lifetime,
cache exclusion, native installer integrity checks and the Windows process handoff.
Both generic worker entry routes reject `app_update_*`; update worker calls are
constructed exclusively by the native update commands.

Native commands are `app_update_status`, `app_update_check`,
`app_update_download`, `app_update_cancel`, and
`app_update_install({acknowledged, unattended})`. Check/download promises settle
when the operation ends, while status and cancellation remain callable. The
main UI may hide its update panel without cancelling an operation. Snapshots
use `spike/app-update/v1`; phases are idle, checking, available, current,
downloading, ready, installing, failed, unsupported and cancelled. Fields are
current_version, latest_version, release_url, asset_name, size, received_bytes,
total_bytes, unattended_supported, message and error, when available. Internal
download_url and sha256 fields are removed from native responses. Validated
worker progress also updates the status snapshot.

Only stable three-part versions and a unique
`SPIKE_VERSION_x64-setup.exe` or `SPIKE_VERSION_arm64-setup.exe` are admitted.
GitHub must supply `sha256:HEX` asset metadata; missing integrity evidence is
unsupported, never an invitation to run unchecked setup. This is integrity
against the HTTPS GitHub release metadata, not an independent publisher signature.
Metadata is limited to 2 MiB, installers to 4 GiB, network reads to 20 seconds
per socket timeout, and downloads to 30 minutes plus host cancellation overhead.
Redirects are restricted to the original release path or GitHub's dedicated
`release-assets.githubusercontent.com/github-production-release-asset/` route.
Download uses exclusive partial creation, exact size/hash checks, fsync and an
atomic final rename. User cancellation kills the owned download worker and
removes partial setup artifacts after the worker ends.

## Cache and handoff

The cache is `%LOCALAPPDATA%/SPIKE/updates/v1`, identified by an exact owner
marker. Symlink/junction/reparse ancestors are rejected. A Windows exclusive
file lease prevents two application instances from cleaning/downloading into
the same cache. Deletion is limited to four fixed names: setup.partial,
setup.exe, update-helper.exe and outcome.json. There is no recursive delete,
caller-supplied cleanup path or project-directory traversal. The marker and
lease file remain. A live helper prevents startup cleanup from deleting its
image; interrupted cleanup is reported and retried on a later check/startup.

Install requires an explicit acknowledgment after the UI has saved and closed
all project state and detached drafts. Native install additionally requires the
main window, no detached windows, no inflight generic worker calls and a ready
installer. New worker calls are rejected during handoff. The native host locks
setup against modification/deletion and rechecks its exact size and SHA-256.
It copies the current executable into the cache as a small-purpose helper mode,
then waits for that helper to independently verify setup and pin the parent
process handle. Failed helper preparation preserves the UI. A remaining resident circuit worker blocks installation until its sessions are
closed normally; no renderer or resident worker is killed by update preparation.

The native host checks for detached windows again after helper verification and
aborts the helper if a tool opened during preparation. The helper requires a
private stdin acknowledgment and actual parent process
exit before executing setup. This mode is intercepted before Tauri initialization
and runs from the copied image, so installed app/worker files can be replaced.
The setup command always includes `/UPDATE`, and includes the fixed `/S` switch
only after explicit background-install selection for an admitted NSIS asset.
The existing generated Tauri NSIS installer tests UpdateMode before its normal
reinstall/uninstall decision and preserves application data in update mode.
NSIS documents `/S` at
https://nsis.sourceforge.io/Which_command_line_parameters_can_be_used_to_configure_installers.
Administrative elevation prompts may still appear.

The helper waits for setup exit and then deletes only setup.exe. Failed setup
or cleanup records a bounded outcome for the next startup; startup displays
that outcome before cleaning old artifacts. The copied helper is removed at
the next safe startup because Windows cannot delete its running image. An
installer exit code is not independent evidence that the new version works.

## Verification limits

Unit tests use synthetic release metadata and byte streams; no installer is
executed. Native tests exercise boundary/integrity behavior. Public latest
release requests returned HTTP 404 during implementation, so published asset,
clean-machine, offline, real upgrade, uninstall, packaged helper and elevation
qualification remain release gates. The package must rebuild the worker to
include the new Python service before distributing this feature. Linux and
macOS automatic setup are unsupported; no guessed installer is executed.
