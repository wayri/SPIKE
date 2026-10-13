# In-app SPIKE updates

Open **Help → SPIKE updates**, **Settings → General → SPIKE updates**, or search
for **SPIKE updates** with Ctrl+K. The separate Windows & tools taskbar restores
the update panel after hiding it.

The official source is [wayri/spike](https://github.com/wayri/spike). Checks use
GitHub's latest stable release API. Only a supported Windows architecture and
the matching SPIKE NSIS setup asset can be admitted. Missing releases, unavailable
network access and missing published SHA-256 digests are reported; an unverified
download cannot be installed. A GitHub digest verifies consistency with the
published asset, not an independent publisher signature.

## Download and install

1. Check GitHub and review the selected version and installer size.
2. Download in the background. Hide the panel and keep working if needed.
   Cancellation discards the partial installer. Check again before retrying.
3. Save and close the project and all SPICE, Python, harness, topology and
   assistant editors. Finish or cancel running work. Assembly drafts block updates.
4. Read the warning and confirm that your work is saved and closed.
5. Install. SPIKE exits before the cache helper launches setup. Do not reopen it
   until setup finishes. Optional background installation uses the admitted NSIS
   silent mode; interactive setup is the default.

Startup checks and automatic downloads are optional local preferences.
They never authorize installation, closing work, or discarding changes.

## Scope and recovery

The updater never deletes projects, board files or saved results. Its cleanup
scope is the application's dedicated update cache and its recorded filenames.
Setup is run in update mode against the SPIKE installation. Installer cleanup
runs after setup exits; leftover helper and partial files are handled on the
next startup. Cleanup failures remain visible instead of broadening deletion.

The native main window owns update state, release/version admission, cancellation
and installer handoff. The frontend supplies no download URL, executable path,
digest or arbitrary installer arguments. HTTP/download orchestration is in
`python/spike_core/app_updates.py`; the narrow native process/cache boundary is in
`app/src-tauri/src/app_updates.rs`. Worker-route restrictions prevent bypassing
the updater through generic calls.

UI guards and focused tests are separate from a real upgrade. A release must
publish a matching installer with GitHub's SHA-256 digest, and Windows upgrade
execution must be qualified before claiming an installed version was updated.
