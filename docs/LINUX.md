# Linux Desktop Build

SPIKE's application shell and Python worker are platform-neutral. The packaged UI does not require Node.js or npm; those tools are build-time dependencies only.

## Ubuntu/Debian prerequisites

Install the Tauri 2 system packages, Python 3 development/runtime support, Node.js, and Rust. The exact WebKit package name depends on the distribution release; current Tauri 2 builds use WebKitGTK 4.1.

Run:

```bash
./scripts/build_linux.sh
```

The script creates `.venv`, installs the pinned project requirements, builds the frontend, and invokes the native Tauri bundle build. Resulting Debian/AppImage artifacts are under `app/src-tauri/target/release/bundle`.

At runtime SPIKE searches, in order:

1. `SPIKE_PYTHON`
2. the installation/project `.venv`
3. a bundled local runtime
4. `python3` and then `python` on Linux/macOS

Set `SPIKE_WORKSPACE` only when the Python worker source is stored outside the installed resource directory. Production installers bundle `python/spike_core`; numerical dependencies must be supplied by the packaged local Python runtime or the selected Python environment.

## Linux verification

```bash
.venv/bin/python3 -m unittest discover -s tests/python -v
cd app && npm run build
cd src-tauri && cargo test
```

Run these checks on an actual Linux CI runner before publishing an AppImage or Debian package. A Windows cross-check cannot validate WebKitGTK linkage, desktop integration, or distribution-specific shared-library availability.
