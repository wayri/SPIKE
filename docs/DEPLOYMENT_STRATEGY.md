# SPIKE Deployment Strategy

## Distribution products

### Developer mode

Run the React frontend with the Tauri development shell and launch the Python worker from the repository. This mode is for contributors only.

### Community desktop

Ship signed installers for Windows, Linux, and macOS containing:

- Tauri binary.
- Frontend assets.
- Python worker runtime or a compiled worker executable.
- Required solver libraries.
- Versioned example projects.
- License notices and model limitations.

The installer also includes a signed `dependencies.lock.json` manifest and a
platform-specific runtime bundle. Core features must not depend on a user's
global Python, Node/npm, Visual Studio runtime, or shell PATH. The application
dependency manager reports each component as `bundled`, `ready`,
`development_host`, or `unavailable`.

Required bundled components are the Tauri frontend assets, compiled SPIKE
worker with its pinned Python runtime (or an equivalent native worker),
contract schemas, and report templates. OpenFOAM, FreeCAD, and Blender are
optional version-pinned bundles. They are supplied through signed release
packages or explicit offline administrator packages; SPIKE never runs
`npm install`, `pip install`, or arbitrary post-install scripts at runtime.

openEMS, FastHenry, and FastCap follow the same optional-engine policy. SPIKE
may detect an administrator-provided installation or install a signed,
version-pinned offline engine package after explicit user approval. Every
package requires recorded origin, hash, license notice, supported platforms,
adapter version, and validation baseline. External executables run in private
job directories with fixed arguments, bounded resources, and no implicit
network access.

The installed app must not require KiCad, Python, Visual Studio, or a global package installation for standalone analysis.

### Current Windows build status

The current Windows engineering-preview build produces a packaged worker plus
NSIS and MSI installer artifacts. The worker is assembled offline-first with PyInstaller
6.21.0, the ABI-matched native PEEC extension, and a SHA-256 file manifest.
The build requires health, native-capability, and permanent 10-case benchmark
smoke gates before the worker is accepted. Tauri launches this bundle before
using the repository Python development fallback.

This is a build artifact, not a completed stable-release qualification. The
following acceptance work remains pending:

- clean-machine Windows install and first-launch verification;
- installer signing, signature verification, and upgrade acceptance;
- uninstaller acceptance and preservation/removal policy verification;
- portable-Windows artifact acceptance;
- Linux and macOS runtime, installer/package, and release-artifact builds.

The packaged worker's native PEEC and shared-reference AC PDN multiport paths
remain approximate. A successful package smoke gate must not be described as
solver signoff or as validated physical capacitor placement.

### CAD adapters

SPIKE treats source integrations as optional adapters rather than product-specific
commands. An adapter may import a signed snapshot, map canonical object identities,
or return result annotations, but it must not expose solver state or vendor objects
to the solver layer. The standalone shell does not provide a "Select in KiCad"
command.

Adapters must never install packages into a CAD application's interpreter or run a
shell-built command string with unescaped paths. Standards-first import remains the
default route; native vendor adapters require a documented fidelity need and legal
review.

### CI/headless

Provide a stable command such as:

```text
spike inspect design.kicad_pcb --format json
spike analyze project.spike.yml --output results/
spike report results/analysis.json --format html
```

Exit codes must distinguish success, warnings, validation failure, solver failure, and unsupported analysis.

## Release channels

- `nightly`: automated builds and experimental capabilities.
- `beta`: design-partner builds with diagnostic logging.
- `stable`: validated solver modes only.
- `lts`: optional enterprise channel with extended support.

Numerical behavior changes require a validation report and changelog entry. UI-only changes can ship faster, but must preserve project and result compatibility.

## Upgrade and compatibility policy

- Every project and result carries a contract version.
- Readers must support at least one previous contract version.
- Migrations are explicit and produce a backup.
- Solver versions are recorded in reports.
- No silent recalculation of old results.
- A result always states whether it is comparable with another result.

## Privacy and security

- Local mode never uploads design data.
- Cloud mode is opt-in and visibly marked.
- Customer files are encrypted in transit and at rest.
- Hosted jobs have retention controls and deletion APIs.
- Logs redact credentials and file contents by default.
- Signed binaries and dependency manifests are published.
- Dependency manifests include component versions, platform, license notices,
  provenance, and SHA-256 hashes for release artifacts.

## Operational monitoring

Collect only opt-in telemetry. Prefer anonymous product health events: launch success, importer failure code, solver completion category, and application version. Never collect PCB geometry or proprietary design data without explicit consent.
