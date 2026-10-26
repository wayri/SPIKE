# IBIS and spatial SI deployment integration, 2026-10-25

Status: source integration and one experimental Windows x64 frozen candidate verified; installed delivery pending.
This record concerns collection, transport and fixture inclusion. It does not
change a numerical method or qualify IBIS/PCB physics.

## Changes and reproduction

`app/src-tauri/tauri.conf.json` includes the small original `examples/si`
fixtures as installed resources. Existing `prepare_release_resources.py`
stages current unignored source and excludes bytecode/cache files; no new
staging algorithm was needed. A small temporary fixture-root test checks the
actual resource map, byte-identical input copying and replay from the stage
without copying a native worker.

`build_packaged_worker.py` explicitly collects the IBIS and spatial service
owners plus the lazy IBIS execution module. Its post-build execution probes
now run `verify_si_ibis_spatial_runtime.py` and its source-coherence check
requires the seven SI service/compiler/parser/line owner modules. The standalone
guard exposes `--require-si-ibis-spatial`; missing modules and stale compiled
code fail before the builder writes a success manifest.

From the repository root, use the prepared release Python environment:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.venv/Scripts/python.exe scripts/verify_si_ibis_spatial_runtime.py
.venv/Scripts/python.exe -m unittest tests.python.test_si_ibis_spatial_packaging tests.python.test_packaged_source_coherence tests.python.test_build_packaged_worker tests.python.test_prepare_release_resources tests.python.test_prepare_release_resources_overrides -v
.venv/Scripts/python.exe scripts/check_architecture.py
```

After building a fresh candidate worker, check the frozen boundary and then the
actual staged/installed fixture root explicitly:

```powershell
.venv/Scripts/python.exe scripts/verify_packaged_source_modules.py <candidate-worker.exe> --require-si-ibis-spatial
.venv/Scripts/python.exe scripts/verify_si_ibis_spatial_runtime.py --worker <candidate-worker.exe> --resource-root <staged-or-installed-resource-root>
```

The latter command invokes a worker with repository-side verification tooling;
it is not an installed end-user command or an installer qualification.

## Executed evidence

- Python 3.12.9, PyInstaller 6.21.0 in `.venv`.
- Source service probe passed: inert IBIS compilation, exact request/deck
  SHA-256, inert runtime identity inspection, current geometry digest,
  raw-to-spatial probe mapping and explicit experimental limitations.
- Generated fixture deck SHA-256:
  `e76ee4705396f93b7f22b0a84c099b7e7b3c2eb23eb11d42d243a37698ffad08`.
- Spatial fixture: 32 victim-stroke positions at three frequencies. Each
  complex voltage equalled its returned raw solver probe. These are transport
  and provenance assertions, not independent numerical accuracy or convergence
  evidence.
- 20 focused tests passed, including missing/stale frozen owner rejection,
  stale geometry/corrupted display value/status rejection and staged fixture
  replay. The tests ran outside the sandbox because its temporary-directory
  ACLs prevented fixture creation and cleanup. No assertions were waived.
- Architecture guard passed.
- Read-only archive inspection of the existing
  `app/src-tauri/resources/worker/spike-worker/spike-worker.exe` found none of
  the seven required SI owner module keys. That existing artifact was not
  replaced or promoted as current.

## Experimental frozen candidate

One explicitly authorized isolated build completed with exit code zero and all
existing qualification gates intact:

```powershell
.venv/Scripts/python.exe scripts/build_packaged_worker.py --candidate-root build/si-ibis-spatial-worker-r1-20261025 --native-kernel-dir build/ac-cht-alpha2-native-cht-current-20261024/Release
```

The fresh candidate kept shared worker resources and runtime-qualification
reports unchanged. Existing first-party native binaries were reused; no native
kernel was rebuilt. The log is
`build/si-ibis-spatial-worker-r1-20261025.log`. PyInstaller completed collection
at 107.186 seconds; runtime verification followed before the success manifest.
Disk free space after work cleanup was 4,902,637,568 bytes, above the reserved
1 GiB headroom.

Artifact root: `build/si-ibis-spatial-worker-r1-20261025`.

- `resources/spike-worker/spike-worker.exe`: Windows x64, Python 3.12.9,
  PyInstaller 6.21.0; 19,571,289 bytes; SHA-256
  `7e22a444216d4ef9cc87b20283dece6b4941882653201527eae065a78b14b7a1`.
- `resources/spike-worker.manifest.json`: 288,519 bytes; SHA-256
  `3d74be9cffd288b2818356fb24e1a88c63a62eb47818f6be7d8a6f4eb8335f43`.
  It binds 1,478 payload files totalling 278,698,630 bytes, all 15 permanent
  benchmarks and eight successful source/frozen runtime comparisons.
- Exact source coherence: 555 checked Python modules, zero changed, missing
  or required-missing modules, including all seven mandatory SI owners.
  All 265 packaged JSON schemas match source.
- Existing extension, EM co-simulation, native CHT/momentum/tetrahedral CHT,
  native interactive engine and PAM3 verification remained enabled and passed.
  The new frozen SI probe passed with the same IBIS deck digest, 32 spatial
  positions and three frequencies; native IBIS execution was not requested.
- Only the small original SI examples were additionally copied beside the
  candidate to `resources/examples/si`, following the current unignored source
  inventory and excluding caches. A fresh worker replay against that staged
  resource root passed. `si-fixture-replay.json` binds all 16 copied files
  (416,666 bytes) by SHA-256 and retains the probe output. Its SHA-256 is
  `bd177b49ad33e59037afdf4437140156cc8105ec9ec5fd86083fa94483ca02c9`.

The worker manifest binds the worker subdirectory; the separate replay report
binds the adjacent SI fixtures. These files form an experimental candidate,
not a complete desktop installer or an approved release.

## Remaining deployment gates and limits

No installer or published release was rebuilt or replaced. Clean-machine,
offline, upgrade and uninstall tests required by `CONTRIBUTING.md` remain
pending. The source/frozen probes use the repository's `SPIKE_HOME` and local
optional runtime discovery; they do not establish a clean installed runtime.
The old shared worker remains unchanged and does not deliver these SI routes.
No commit, tag, push, installation or publication was performed.

ngspice remains an optional separately managed trusted native runtime. Existing
discovery checks PATH, the registered engine or `SPIKE_NGSPICE_HOME`, then
`SPIKE_HOME/runtime/external/Spice64` and `ngspice`. No new ngspice binary,
dependency, distribution license or implicit native execution was added. The
probe only inspects runtime identity (`executed=false`); source inspection found
an available local runtime. That observation is not an installed-runtime claim.
Actual execution still requires explicit runtime path, exact SHA-256 and intent.

IBIS results remain experimental and `production_qualified=false`. Spatial
results use supplied even/odd RLGC parameters and returned RMS phasor voltage
on an explicitly assigned stroke. They do not establish material extraction,
a surrounding field, transient coupling or protocol compliance. Native IBIS
execution, numerical fixture convergence, vendor-model coverage and knowledgeable
human numerical review remain separate gates; this transport check closes none
of them.
