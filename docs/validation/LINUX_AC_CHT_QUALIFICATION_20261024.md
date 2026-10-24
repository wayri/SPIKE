<!-- SPDX-License-Identifier: Apache-2.0 -->
# Linux AC/CHT source qualification - 24 October 2026

## Scope and conclusion

This records four native Linux layers on the existing Ubuntu WSL environment:
the initial system-Python source qualification, the first isolated 16-package
frozen-worker qualification, and a separately retained Windows-source-matched
`0.4.0-alpha.2` preview candidate, followed by the final corrected-baseline R4
same-source worker candidate. Each layer is bound to the source hashes in
its reports; Git HEAD `537023f84e70ed0d45915c7ef2b5cdb858d18228` is context,
not the cross-platform coherence proof. This is not a Flatpak, installed
payload, clean-machine, GUI, or non-WSL Linux qualification.

The AC resistor-to-solid-to-fluid CHT analytical refinement benchmark and the
fresh-process runtime/memory benchmark passed on Linux. The initial focused
source run passed 52 of 54 tests and exposed a real SciPy 1.11.4 API mismatch:
its `minres()` accepts `tol`, while the source then called `rtol`. After the
compatibility fix, both formerly failing cases and both new compatibility tests
passed, and fresh R2 benchmark reports passed against the changed source. The
new public worker/service/CLI route first passed its five dependency-independent
tests. A subsequently authorized, isolated, hash-locked schema environment made
the schema-resolution test executable; the complete 62-test focused suite then
passed. The two frozen-worker candidates subsequently passed their bounded
worker checks. Flatpak and installed-application lifecycle layers remain
explicit release blockers, not waived.

## Environment and packaging boundary

- Ubuntu 24.04.3 LTS under WSL2, Linux kernel
  `6.6.87.2-microsoft-standard-WSL2`, x86-64.
- Native `/usr/bin/python3`, Python 3.12.3; NumPy 1.26.4 and SciPy 1.11.4 from
  Ubuntu `/usr/lib/python3/dist-packages`.
- Numerical commands set `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`,
  `MKL_NUM_THREADS=1`, and where applicable `SPIKE_BLAS_THREADS=1` before the
  first NumPy/SciPy import. The runtime/memory harness separately measured its
  own backend-default and explicit-one-thread fresh-process environments.
- No Linux project virtual environment was found. Every discovered project
  `pyvenv.cfg` names a Windows interpreter and was not used.
- At initial discovery, `cmake`, `ninja`, `gcc`, and `g++` were available;
  `flatpak`, `flatpak-builder`, PyInstaller, pytest, and Linux GUI bindings were
  absent. No system package was downloaded or installed. PyInstaller and its
  exact reviewed closure were later installed offline into an isolated ext4
  venv solely for the frozen-worker layers. No Flatpak build, installed desktop
  launcher, upgrade, uninstall, clean-machine, or GUI claim is made.

Exact OS/package evidence and the observed SciPy signature are recorded in
`build/linux-ac-cht-20261024/environment.txt`.

## Executed evidence

### AC/CHT refinement

`scripts/benchmark_em_network_cht.py` passed both predeclared families at
levels 1, 2, and 4. The finest relative temperature-rise L2 errors were
`0.031832810101166585` for conduction limit and `0.03170819736416717` for
tangential shear, below the unchanged `0.05` limit. Observed orders were above
`2.07`, above the unchanged `0.8` minimum. The shear case had nonzero solved
mass flow. Source hashes were unchanged across the run. This remains the
benchmark's stated synthetic, experimental scope and does not promote general
PCB cooling or production qualification.

### Fresh-process runtime and memory

Two measured fresh processes per configuration, after one discarded warmup,
passed all seven recorded gates: unchanged sources, the independent matched-AC
oracle, CHT cell/global energy defects, mixed residual, nonzero flow,
cross-configuration numerical equivalence, and identical input digests. Median
solve times were `0.207365919 s` backend-default and `0.221885644 s`
explicit-one-thread. Median post-solve peak resident memory was `67,905,536`
and `67,915,776` bytes respectively. Linux private-commit metrics are correctly
reported as `null`; the small timing difference is not a performance claim.

### Focused tests and release route

The initial 54-test numerical-runtime, observer/harness, AC resistor-CHT, tetra
energy, tetra CHT, and tetra Stokes run completed in 44.419 seconds: 52 passed
and two failed. Both failures returned the structured blocked result
`CFD_TETRA_STOKES_REJECTED` with `minres() got an unexpected keyword argument
'rtol'`; the Linux SciPy signature recorded in the environment evidence is
`minres(..., tol=1e-05, ...)`.

After the source selected `tol` or `rtol` by inspected signature while retaining
the exact `1e-14` tolerance and independent residual gate, the two formerly
failing solver tests and two new API/error-path compatibility tests passed in
28.817 seconds. No TypeError retry path is involved. The complete refinement
and fresh-process runtime/memory benchmarks were then rerun as R2 and passed;
their source hashes bind the post-fix state.

The initial six-test public release-route run exercised the direct service, fresh
JSON-line worker, CLI spelling, structured child failure, and malformed-input
rejection. Five passed. Schema resolution alone errored at import with
`ModuleNotFoundError: No module named 'referencing'` in the unmodified system
interpreter. Those same five routes passed again after the solver fix; this
deliberately does not relabel the missing schema test as passed.

An isolated schema-only environment was then provisioned on WSL ext4 from six
reviewed binary wheels. The initially authorized five-wheel set was rejected
before installation because `referencing==0.37.0` declares
`typing-extensions>=4.4.0` on Python below 3.13. After explicit authorization,
the existing reviewed `typing_extensions==4.16.0` pin completed the closure.
No source distribution or unpinned dependency was admitted. Installation used
`--no-index`, `--only-binary=:all:`, and `--require-hashes`; `pip check` reported
no broken requirements.

The complete run combined the original 54 focused tests, two MINRES API/error
path tests, and all six public schema/service/worker/CLI route tests. All 62
passed in 68.269 seconds. The environment report proves that all six schema
packages resolve from the isolated venv, while only the previously qualified
NumPy 1.26.4 and SciPy 1.11.4 resolve from Ubuntu system site-packages. BLAS
variables were set to one before imports.

## Schema provisioning evidence and remaining packaging plan

No relevant wheels were present in the existing Linux pip cache. The WSL ext4
filesystem has about 926 GiB free, while the mounted Windows `C:` volume has
only about 8.1 GiB free and reports 100% use after rounding. Any authorized
Linux build environment and Flatpak objects should therefore live on WSL ext4
(for example a new `/home/gulkak/...` directory), with only final reviewed
artifacts copied to the repository after a size check.

The schema-only repair used a fresh Python 3.12 venv with the repository pin
`jsonschema==4.25.1` and a generated **Linux CPython 3.12 x86-64** hash lock for
its transitive closure. Existing reviewed Windows pins supplied the reviewed
versions and expected pure-wheel hashes:
`attrs==26.1.0`, `jsonschema==4.25.1`,
`jsonschema-specifications==2025.9.1`, `referencing==0.37.0`, and
`rpds-py==2026.6.3`. Their reviewed Windows wheel SHA-256 values are recorded in
`requirements-runtime-windows-x64.txt`; respectively the directly relevant
values include
`c647aa4a12dfbad9333ca4e71fe62ddc36f4e63b2d260a37a8b83d2f043ac309`,
`3fba0169e345c7175110351d456342c364814cfcf3b964ba4587f22915230a63`,
`98802fee3a11ee76ecaca44429fda8a41bff98b00a0f2838151b113f210cc6fe`,
`381329a9f99628c9069361716891d34ad94af76e461dcb0335825aecc7692231`,
and `2c958bf94822e9290a40aaf2a822d4bc5c88099093e3948ad6c571eca9272e5`.
The pure-wheel hashes matched. The platform-specific Linux
`rpds_py-2026.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl`
has SHA-256
`ecabd69db66de867690f9797f2f8fa27ba501bbc24540cbdbdc649cd15888ba6`.
The admitted `typing_extensions` pure wheel has SHA-256
`481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8`.
Five wheel metadata records declare MIT; `typing_extensions` declares PSF-2.0.
Each archive contains retained license-file evidence. Metadata, tags,
requirements, license-file hashes and archive hashes are in
`schema-wheel-review.json`.

Worker freezing additionally requires the source-enforced
`PyInstaller==6.21.0`, with Linux wheels for its exact transitive build-only
closure. The existing Windows build lock records `altgraph==0.17.5`,
`packaging==26.0`, `pyinstaller-hooks-contrib==2026.6`, and
`setuptools==84.0.0`; Windows-only `pefile` and `pywin32-ctypes` must not be
copied into a Linux lock. The reviewed Windows hashes are platform evidence,
not Linux install hashes. The component inventory records PyInstaller as GPLv2,
altgraph as MIT, and retains wheel-metadata license evidence for hooks-contrib;
Linux wheel metadata and bundled license files still require review before use.

The repository's actual Linux release recipe also requires Ubuntu packages
`ninja-build`, `libeigen3-dev`, `libwebkit2gtk-4.1-dev`,
`libappindicator3-dev`, `librsvg2-dev`, `patchelf`, `flatpak`, `xvfb`, and
`dbus-x11`, plus user-scoped Flathub `org.gnome.Platform//50` and
`org.gnome.Sdk//50`. In the current environment, Flatpak and
`libappindicator3-dev` are absent; the other principal packages are present
(the installed `xvfb` is behind its current candidate). Before any authorized
system change: capture the exact apt transaction with simulation, review
licenses and download sizes, install only the missing pinned Ubuntu packages,
then inspect the GNOME 50 remote runtime sizes and commit identities before a
user-scoped install. Build, frozen-worker verification, offline Flatpak launch,
installed CLI, reinstall, uninstall, final payload hashing, and GUI smoke remain
mandatory distinct gates.

## Isolated frozen-worker qualification

A separate no-system-site Python 3.12 venv and source snapshot were created on
WSL ext4. The snapshot is a copy of the active working tree with `.git`, virtual
environments, dependencies, and generated build trees excluded. It is therefore
identified by the individual source hashes in `linux-worker-environment.json`,
not by Git HEAD and not by the Windows candidate's source identity. No coherent
cross-platform release claim is made without an owner-hash comparison.

The minimal worker lock contains 16 exact binary-wheel packages: the six schema
packages above plus PyInstaller 6.21.0, altgraph 0.17.5, nanobind 3.0.0, NumPy
2.5.2, packaging 26.0, PyArrow 25.0.1, PyInstaller hooks 2026.6, SciPy 1.18.1,
setuptools 84.0.0, and Shapely 2.1.2. The 10 newly staged archives total about
108.4 MB. They were reviewed for tags, requirements, licenses, retained license
files and hashes, then installed offline with `--no-index`,
`--only-binary=:all:` and `--require-hashes`; `pip check` passed. This runtime's
NumPy 2.5.2/SciPy 1.18.1 evidence is separate from the Ubuntu-system NumPy
1.26.4/SciPy 1.11.4 source-suite evidence and from the Windows runtime.

The repository-pinned `nanobind==3.0.0` wheel was yanked by its publisher for
mistakenly declaring Python 3.9 compatibility. The candidate uses Python 3.12,
and the reviewed wheel hash matches the repository's existing lock, but the
yank status is retained as an advisory and not concealed.

The existing Ubuntu CMake 3.28.3, Ninja 1.11.1, GCC/G++ 13.3, Eigen 3.4.0 and
patchelf 0.18 prerequisites built all three required native payloads inside the
snapshot. Native airflow and CHT CTests passed 2/2 in 92.59 seconds. The PEEC
extension, owned SPIKES C API library and airflow executable are native x86-64
ELF artifacts; exact hashes are recorded in `linux-worker-native-sha256.txt`.

The candidate-root PyInstaller build completed and its complete mandatory
source-versus-frozen runtime qualification passed all eight required snapshot
checks. The integrity manifest identifies worker `0.4.0-alpha.2`, every packaged
file, native payload identities and successful native probes. The retained
payload has 518,368,851 logical bytes, occupies approximately 312 MiB on WSL
ext4, and contains 1,201 files; it was intentionally not copied to the nearly
full Windows volume. PyInstaller emitted one analysis warning for
the absent private `scipy.special._cdflib` hidden import; the mandatory frozen
runtime, benchmark and numerical probes nevertheless executed successfully,
so it is retained as analysis evidence rather than silently suppressed.

The separate frozen-worker EM co-simulation probe also passed. It executed the
public preparation, AC solve, resistor-to-thermal, resistor-to-CHT and owned
SPICE methods. The deposited CHT resistor heat was 0.02 W, cell-energy relative
defect was `1.7347234759768068e-16`, solved flow was nonzero, and the independent
thermal oracle produced 300.015 K. The report retains
`production_qualified: false` and its synthetic-packaging/no-measured-EM scope.

The actual retained executable is
`/home/gulkak/spike-linux-worker-20261024/src-min/build/linux-worker-candidate/resources/spike-worker/spike-worker`,
SHA-256
`3339fc493d1ba738793eced58ec5443b87b5458a96094956b0ad3227fce3d0ed`.
The adjacent ext4 integrity manifest is represented by the retained evidence
copy `linux-worker-manifest.json`, SHA-256
`71df31080e8243508576074415c83bd265a2bbae5d8e83380f483044e35d6dfe`.
The executable was passed directly to `verify_packaged_cli.py -- ... --cli`;
all 106 help surfaces plus version, inspect and structured-error probes passed,
reporting `SPIKE CLI 0.4.0-alpha.2`. No source launcher substituted for the
packaged side of the comparison.

The full analytical AC/CHT refinement benchmark was also rerun after freezing
under the same clean 16-package venv. Both families passed all unchanged gates,
and the immutable report records unchanged owner hashes. Finest relative-rise
L2 errors were `0.03183281010116648` and `0.031708197364167176`, with observed
orders above 2.07.

The Windows inspected baseline
`build/ac-cht-alpha2-worker-20261024/inspected-source-baseline/SOURCE_SNAPSHOT.json`
was compared byte-for-byte against every corresponding file in the Linux ext4
snapshot. Of 771 baseline files, 767 were equal, four differed and none were
missing. The changed paths are `python/spike_core/component_thermal.py`,
`service_assembly_handlers.py`, `service_simulation_handlers.py`, and
`thermal_network.py`. Every baseline-covered AC/CHT/runtime owner explicitly
checked—tetra mesh/Stokes/energy/CHT, EM-network AC/resistor-CHT, numerical
runtime, service, CLI and contract catalog—was equal. The process-memory
observer was not part of the Windows inspected baseline, so no cross-platform
equality is claimed for it. The complete per-path hashes and changed list are
retained in `linux-vs-windows-source-comparison.json`; this evidence supersedes
any inference based only on Git HEAD.

### Windows-source-matched alpha.2 preview

A fresh sibling source tree was materialized at
`/home/gulkak/spike-linux-worker-20261024/src-winmatch-alpha2-r3`. It was copied
from the immutable first Linux snapshot with generated build trees excluded,
then only the four differing Python files named above were replaced with the
exact retained Windows inspected-baseline bytes. The first Linux snapshot,
first frozen candidate and their evidence were not overwritten or relabelled.
Two abandoned partial copy directories remain separate from this candidate;
neither was frozen or used as evidence.

Before freezing, every one of the 771 paths in the Windows
`SOURCE_SNAPSHOT.json` matched byte-for-byte: 771 equal, zero changed and zero
missing. All 78 files below the native `src` and `python/bindings` inputs also
matched the first Linux snapshot. The already-built native payloads therefore
remained applicable and retained their hashes; no native source or compiler
input changed as part of this four-Python-file materialization.

The same reviewed no-system-site 16-package venv froze a new candidate at
`/home/gulkak/spike-linux-worker-20261024/src-winmatch-alpha2-r3/build/linux-worker-winmatch-alpha2/resources/spike-worker/spike-worker`.
The executable is 13,509,408 bytes with SHA-256
`1981eccdc5c1ac22127202cf6097e86d38435334241ed72ff008769d6a2c1177`;
its manifest SHA-256 is
`2090842959a4d5564cb0a2151bab7723863ef61387e6e0bd3dfbb9b8bed429d7`.
The builder's complete eight-check source-versus-frozen qualification passed.
The previously retained absent-private-`scipy.special._cdflib` analysis warning
recurred unchanged and was not suppressed.

The independent frozen EM/co-simulation probe passed preparation, matched AC,
resistor thermal, resistor CHT and owned SPICE execution. It retained 0.02 W
CHT resistor heat, `1.7347234759768068e-16` cell-energy relative defect,
nonzero flow, the 300.015 K thermal oracle and `production_qualified: false`.
Direct execution of the frozen binary through `verify_packaged_cli.py` passed
all 106 help surfaces, version `SPIKE CLI 0.4.0-alpha.2`, inspect and structured
error checks. The post-freeze source refinement benchmark also passed unchanged
gates, with finest errors `0.03183281010116648` and
`0.031708197364167176` and observed orders above 2.07.

The final frozen-runtime refinement replay used
`scripts/verify_packaged_ac_cht_refinement.py` directly against this executable
and the independently qualified retained reference at
`build/em-network-cht-runtime-20261024`. Its reference report SHA-256 was
`908e1b20a31aeb5d1e671276dea738304fc390882a820710040466efdc9d5acd`.
All six conduction-limit and tangential-shear requests at levels 1, 2 and 4
passed through the public frozen-worker method. The verifier compared the full
AC sample arrays and full CHT physical fields with unchanged relative and
absolute tolerances of `1e-10`, retained the `1e-9` cell/global energy gates,
and confirmed the worker, verifier, reference report and all referenced inputs
were unchanged before and after execution. This is transport/field equivalence
to retained analytical qualification, not another independent physical
reference or production qualification. Full per-case results remain on ext4 at
`/home/gulkak/spike-linux-worker-20261024/winmatch-ac-cht-refinement-replay`;
only the small final report and log were copied into repository evidence.

This candidate establishes coherence for the 771 Python/schema files retained
from the Windows inspected artifact. It deliberately excludes the four later
live-workspace changes from both platform previews and does not claim complete
native-source or whole-release byte identity beyond the separately recorded
Linux native-input equality. No payload was copied from ext4 to the
space-constrained Windows volume.

### Final corrected-baseline R4 same-source worker pair

After the corrected Windows R3 worker baseline became available, another fresh
sibling was materialized at
`/home/gulkak/spike-linux-worker-20261024/src-winmatch-alpha2-r4`. The complete
retained baseline at
`build/ac-cht-alpha2-final-worker-r3-20261024/inspected-source-baseline` was
overlaid exactly; live source roots and every preceding Linux candidate were
left unchanged. Its `SOURCE_SNAPSHOT.json` has SHA-256
`80cc0a91ee9d868a136781ff775236b423fdfdd4282fb281f3ce2ce4e212e094`
and records 510 modules plus 265 schema JSON files. All 775 retained paths
matched byte-for-byte before freezing: 775 equal, zero changed or missing.
This includes the bounded Windows rename correction, corrected SI-08 schema
identifiers and newly retained source handlers. The previously qualified Linux
PEEC, SPIKES C API and airflow/CHT native artifact identities were unchanged.

The final Linux executable is
`/home/gulkak/spike-linux-worker-20261024/src-winmatch-alpha2-r4/build/linux-worker-winmatch-alpha2-r4/resources/spike-worker/spike-worker`.
It is 13,527,664 bytes with SHA-256
`996a5e1c67d89669de16bb463b125893e8d4fe473b6417886e2267720b5d730b`;
the manifest SHA-256 is
`b45b91285537eea1a0a20e10d2b8a9fa35efc9b8901ccf239feba5408dd8faa2`.
The same reviewed clean 16-package venv built it without downloads. The
builder's mandatory source-versus-frozen qualification passed all eight checks;
the existing private SciPy hidden-import warning remained visible, and no new
module closure was missing or silently excluded.

The actual frozen EM/CHT probe passed all five public methods and retained its
synthetic, non-production status. Direct packaged CLI verification passed all
106 help surfaces, version `SPIKE CLI 0.4.0-alpha.2`, inspect and structured
error behavior. The full frozen field replay then passed all six retained
conduction-limit and tangential-shear cases against reference report SHA-256
`908e1b20a31aeb5d1e671276dea738304fc390882a820710040466efdc9d5acd`:
full AC sample arrays and full CHT physical fields agreed at unchanged relative
and absolute tolerances of `1e-10`, with the `1e-9` energy gates enforced.
Complete replay results remain on ext4 at
`/home/gulkak/spike-linux-worker-20261024/r4-final-ac-cht-refinement-replay`;
only its small report and log were copied to repository evidence.

This R4 artifact and the corrected Windows R3 worker are the final same-source
Python/schema worker pair. Their platform-native executables are intentionally
different binaries; equality is established for the 775 inspected source and
schema paths, not inferred from Git HEAD. No Linux payload was copied to the
Windows volume.

These checks qualify the three isolated Linux frozen workers within their stated
source identities. Flatpak assembly, installed CLI/desktop launch, GUI smoke,
network-disabled application launch, reinstall, uninstall and clean-machine
behavior remain unverified.

## Reproducers

Run from the repository root in the same Ubuntu environment:

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 SPIKE_BLAS_THREADS=1
python3 -m unittest -v \
  tests.python.test_numerical_runtime \
  tests.python.test_solver_runtime_memory_benchmark \
  tests.python.test_em_network_resistor_cht \
  tests.python.test_cfd_tetra_energy \
  tests.python.test_cfd_tetra_cht \
  tests.python.test_cfd_tetra_stokes
python3 -m unittest -v tests.python.test_em_network_cht_release_route
python3 scripts/benchmark_em_network_cht.py \
  --output build/linux-ac-cht-20261024/refinement
```

The runtime/memory harness intentionally owns the child environments:

```bash
python3 scripts/benchmark_solver_runtime_memory.py \
  --output build/linux-ac-cht-20261024/runtime-memory.json \
  --samples 2 --timeout-seconds 90
```

## Evidence hashes

| Artifact | SHA-256 |
| --- | --- |
| `environment.txt` | `1adcf538604b1b4a25b16a43c08b6acf3768700c72ff4f737349dcd59229df20` |
| `focused-unittest.log` | `72ce676e2be5dcb03f5ac99ba08eaae592d9147234b70fb8a5a1087a2bf639a2` |
| `release-route-unittest.log` | `25e16f717417f18de4579fdf430630b3df4851b37f35cf51f22f489f6af19ab2` |
| `runtime-memory.json` | `457896c2a0392111c648a8b4eb5d5fd8a7ffaea043cea77c436e5242dff8f88c` |
| `refinement/report.json` | `9bab9fdf92b498857ecfaad4e0c783046f20646fd8243202bde5bfbd3cdf40a7` |
| `minres-compatibility-rerun.log` | `e55f25a68643239551f1b0fe4f2fb63789cd9e6ff0a9baf42aafd5fed0b60493` |
| `release-route-rerun-without-schema.log` | `906964de4b368db2933ffc35420591ad238cc430fe83f15a7e658198b1a3b9d3` |
| `runtime-memory-r2.json` | `295c30105ee31648ff5c69f21b1ce9877736f8e8dd0971e27bd3263ee571bb7b` |
| `refinement-r2/report.json` | `884be7a6acfd052c74c059dcfc005d5fba5c95b3ea3c9a97b18743a419196a7a` |
| `requirements-schema-linux-cp312-x86_64.txt` | `dd670fe3369db61fe1b92de640efb475f4c5723057b926c4dfb5e768fb3d8d61` |
| `schema-wheel-review.json` | `ea7bdbe24bb96f494801f4ca32b049f2a395286c2299858bae64f342e07b46f0` |
| `schema-wheel-sha256.txt` | `24728a7c590e2c6dbc05a59a6d75e57eec98511cd21ba2557c6ffb6aadf10a42` |
| `schema-offline-install.log` | `6742c6302424924bdc2acc4c30f2e4d95cde19f190ffdab09806937bcba2a516` |
| `schema-pip-check.log` | `9261363b733079a641c2e4cc9bc46ffa1d8336945a87f807b6cf68847dbc9b09` |
| `schema-venv-environment.json` | `5a33f7aacc31c7f29be85718fa246607aab3cb9d84b284dfbf64982244102425` |
| `schema-venv-focused-62.log` | `be11b59c6c8e26721e8f781936678fd61c16cae9145c99a8338f8d1f306df430` |
| `requirements-linux-worker-minimal-cp312-x86_64.txt` | `e82735fccca54bcffbba5c69ae7e8847f246647681df5640e717f8409fcd9cdf` |
| `linux-worker-wheel-review.json` | `7cc0effaa089ca77130f58774d3f83df2fba630cf88b8fbbe1569422627c445a` |
| `linux-worker-wheel-sha256.txt` | `a040efa54cb69891dc2df4a10b9cb07a8f8cf98135995c041e50e225ac8e4a7f` |
| `linux-worker-offline-install.log` | `d83350ddf806fbf5007af4607c901d9d18f84d51d454125bc556e4458b8ad1ce` |
| `linux-worker-native-build.log` | `89fe50ce77600f256a896be45877f250e9135adee5097738c36b9f42c75b3386` |
| `linux-worker-airflow-build.log` | `e0ea37c92df26ca3f0d2f0b370d3d5865d65e6b735dc69adcfbcecf6a2bfeb37` |
| `linux-worker-native-sha256.txt` | `51e7a49a8ecbb95ac7fbd136f25a233a2ab7e19c189a83182d01da50b4149271` |
| `linux-worker-freeze.log` | `82706a63a65f4a0c9bf15e4fc0f145944e47072587f396ef53d771a736e303b1` |
| `linux-worker-manifest.json` | `71df31080e8243508576074415c83bd265a2bbae5d8e83380f483044e35d6dfe` |
| `linux-worker-runtime-qualification.json` | `81a86904272ce78e59ee814eaea0907cf030df3dccf01ef934514c9849d5c63a` |
| `linux-worker-em-cosimulation-probe.json` | `edab5df4d5650dc61e2d28b5ce5d4b5318fb3e6f4bfb4e8e6c29522221582e02` |
| `linux-worker-environment.json` | `cee6d780685ed4bc0f80dbdb2338d0ac4b7668f541e824056311a13f297d5f76` |
| `linux-worker-packaged-cli.log` | `e840e5cff55cfc719e7a544c53bb0e09ace52daa27d009e3e7d33d0fa7f4ad10` |
| `linux-worker-refinement/report.json` | `bbd42fc91be6cea7a5ae8271b36fffa10320b8f524d2228f6b8b6ee9ab3561a6` |
| `linux-vs-windows-source-comparison.json` | `0418691545e7755dd1fafe9bbfdbeb4fffbb1f463bf526a9208d4427feaed02b` |
| `linux-winmatch-source-comparison.json` | `5c13d3310880fc69c2d4261db253ac02e88b60877144bda57cdaa4f480c9cf6c` |
| `linux-winmatch-worker-freeze.log` | `e218afadb0c7e772bbb098016da86d8ab45dee12c5dd2704c2d6f8e0f74893dd` |
| `linux-winmatch-worker-manifest.json` | `2090842959a4d5564cb0a2151bab7723863ef61387e6e0bd3dfbb9b8bed429d7` |
| `linux-winmatch-worker-runtime-qualification.json` | `9678014780ad39df0492fdc6e140c1f31876d14d9418eef682e6fdccce623f3e` |
| `linux-winmatch-worker-em-cosimulation-probe.json` | `edab5df4d5650dc61e2d28b5ce5d4b5318fb3e6f4bfb4e8e6c29522221582e02` |
| `linux-winmatch-worker-em-cosimulation-probe.log` | `809fbf76ae285810954cdc6077f0de2bc1df489bf95361ee55dc8ce808ce8577` |
| `linux-winmatch-worker-packaged-cli.log` | `5b0deea8a8d7aeddd66f27a565f7a704d4b25e4ea8efc58f60883317de2dfb63` |
| `linux-winmatch-worker-refinement/report.json` | `57fd88ffe7cef57b1efa94ebb7924b4d73b882961ee388310387ca0352cb52a6` |
| `linux-winmatch-worker-refinement.log` | `57fd88ffe7cef57b1efa94ebb7924b4d73b882961ee388310387ca0352cb52a6` |
| `linux-winmatch-worker-artifact-sha256.txt` | `e8339001bbfddda1c96355e02d867a4b49a5384588edc352ff69664212c480b7` |
| `linux-winmatch-worker-ac-cht-refinement-replay.json` | `98e73113d637eeb8147397f93a88f766fec6638ef27f4f932f4846ad0acc8e7f` |
| `linux-winmatch-worker-ac-cht-refinement-replay.log` | `f3aeb0e03846c798bee3c4fe0c81b2c4f4ad22ae84c23505ff9d5752cf919988` |
| `linux-r4-final-source-comparison.json` | `cafc52ba2b307f7a4d3270254dde3ed67359e252891ecf98f04c1d4031a4c8fb` |
| `linux-r4-final-worker-freeze.log` | `3b336798b203c1c96f857d0f47fdea93e2b745d6dff08fbba944958db7096429` |
| `linux-r4-final-worker-manifest.json` | `b45b91285537eea1a0a20e10d2b8a9fa35efc9b8901ccf239feba5408dd8faa2` |
| `linux-r4-final-worker-runtime-qualification.json` | `f00391b324fe998dadc5d360f0a1a7b83f05dc7791c264e40d07bd1a230a4b70` |
| `linux-r4-final-worker-em-cosimulation-probe.json` | `edab5df4d5650dc61e2d28b5ce5d4b5318fb3e6f4bfb4e8e6c29522221582e02` |
| `linux-r4-final-worker-em-cosimulation-probe.log` | `809fbf76ae285810954cdc6077f0de2bc1df489bf95361ee55dc8ce808ce8577` |
| `linux-r4-final-worker-packaged-cli.log` | `bb53f51a14ffb53afa05c9813e9fec8902d63aa030ca39005b8c1270851bc941` |
| `linux-r4-final-worker-ac-cht-refinement-replay.json` | `7f5250a27885f672f36835541978ec24c5a778d5f2c866d98666453ae12abfbf` |
| `linux-r4-final-worker-ac-cht-refinement-replay.log` | `d815dac42d5a7ac3677af65885bd5fd523421fc466679690cc08ab7e5aac8202` |
| `linux-r4-final-worker-artifact-sha256.txt` | `ca719943886ca8d428561efbe7f6caec7f80003f1b2a25e251f5bfba028a6826` |

All paths are below `build/linux-ac-cht-20261024/`. The individual refinement
request/result hashes and the exact owner-source hashes are embedded in the
refinement report; the runtime report contains before/after source hashes and
every measured sample.
