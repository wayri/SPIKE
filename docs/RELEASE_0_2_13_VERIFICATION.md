# SPIKE 0.2.13 engineering preview verification

Date: 2026-09-24. This is an unsigned engineering preview, not a production or physics-qualified release.

## Build and package

- `scripts/build_windows_installer.ps1 -Channel Preview` completed successfully.
- The script passed architecture, error-contract, schema, frontend, and Rust checks (29 Rust tests passed, one live OS test ignored).
- The packaged worker integrity manifest verified after PyInstaller assembly.
- Windows MSI and NSIS installers were produced; SHA-256 values are recorded in the attached `SPIKE-0.2.13-preview-installers.json`.

## Packaged runtime and local installation

- The packaged worker returned `spike/worker-health/v1`, status `ready`, and version `0.2.13`.
- Its `run_python_script` route completed a script and captured `packaged-python-ok`.
- MSI installation returned Windows error 1925 because it requests all-user privileges.
- NSIS `/CurrentUser /S` completed with exit code 0 into `C:\Users\yawar\AppData\Local\Programs\SPIKE`.
- The installed executable reports product version `0.2.13` and matches the built executable's SHA-256: `1d6500e149fde763a189fe6ab366b4e335ee3b4ba3f359a9a0cfccf4e0793bec`.
- The installed worker returned health `ready`, version `0.2.13`, and completed a Python script with `installed-python-ok`.
- Windows still lists the previous `0.2.5` MSI registration. The MSI was not uninstalled because its all-user uninstall needs administrator privileges. This registry entry is stale and should be removed by an administrator before a future MSI upgrade.

No clean-machine install, GUI interaction, numerical signoff, or production signing was performed in this verification.
