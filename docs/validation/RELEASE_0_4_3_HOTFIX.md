# 0.4.3 hotfix scope and verification

Date: 27 October 2026. Base: published 0.4.2,
`390e6d56466955cc7a5ad886ff528a9269a1adb6`.

## Scope boundary

The patch changes workspace/viewport controls, thermal setup routing, power-tree
presentation and inference, UI tests, release versions/documentation and a typed
adapter to the existing normalized PCB copper DC workflow. No new dependencies.
The `calculatePowerTree` declaration matches the baseline after newline
normalization. Pin-role inference changes establish review candidates, not
validated electrical connectivity or revised power-budget equations.

Exact baseline Git tree identities (unchanged in this release):

- `python/spike_core/solvers`: `d042ea443a228ddf81ec12ffd5938b77583cdf0b`
- `src`: `81656fdfb788f6691c40a9a1edc5632f65ad5509`

Outside the UI/tests/docs/version files, the only Python change is the package
version in `python/spike_core/__init__.py`. No changes to numerical kernels,
solver schemas, extensions or native host source. Full imported-part turbulent
CHT, CFD loads, new AC/GHz capability and other later work are excluded.

## Executed checks

Passed in the isolated release checkout:

- `npm run test:ui-hotfix`
- `npm run test:geometry-pi`
- `npm run test:power-tree-editor`
- `npm run test:button-standard`
- `npm run test:parser` (32 copper / 35 total regression fixtures)
- `npm exec tsc -- --noEmit`
- `npm run check:architecture` and `python scripts/check_architecture.py`
- `npm run build -- --outDir ../build/ui-hotfix-frontend --emptyOutDir`
- Release version consistency check: 0.4.3 across package authorities.

Production frontend build retains existing large-chunk and mixed static/dynamic
Plotly import warnings. Focused independent agent review found no blockers in
changed routing, header, rings, power-tree or adapter code; six focused checks
were independently rerun successfully. This is not knowledgeable numerical review.

### Existing solver handoff

The actual TypeScript adapter constructed a request for the unchanged Python
worker service. A declared 10 mm by 1 mm by 35 micrometre copper track with a 5 V
source and 1 A load returned `spike.routed_dc`, approximate status and 12 geometry
faces. Maximum voltage drop was 0.0049261083743843415 V. The result retained
voltage, voltage drop, current, operating-point impedance, current density, power
loss and via-current-density fields. This checks transport and retained fields;
it is not additional numerical qualification.

Request SHA-256: `0236d0c3af1c08bd5a7ae6f9cd66af1d65be7cbfab40eb1108ae60a5a95e5648`.
Response SHA-256: `1bf3858f3d231939575a1e4a7b074acb155b5fec6de8021cd2d3cfbd1622f254`.

### UI observation

A release-checkout Vite preview showed the centered search, right-side utilities
and rotation rings. The Geometry -> basic PI command was present and disabled
without a board. A separately labeled, explicitly authored power-tree acceptance
fixture exercised fit, collapse, reset and readable directional branches. It was
not a board simulation. No new installed-app or narrow native-window acceptance
is claimed. The private preview fixture and screenshots are not release assets.

### Rust and packaging limits

The default Cargo build is blocked by the absent packaged worker resource.
`cargo test --lib --offline` with a test-only `TAURI_CONFIG` empty bundle-resource
override ran 82 cases: 80 passed, 1 failed, 1 ignored. The failing
`resident_packaged_worker_preserves_a_native_spikes_session` requires the missing
packaged worker executable. The ignored test requires live OS GPU counters.
No Rust source was changed to bypass this. Installer and installed-app lifecycle
qualification remain incomplete. This release distributes committed source only.

### Full Python suite

The required command `python -m unittest discover -s tests/python -v` completed
with **5,694 tests, 35 failures, 115 errors and 210 skips** (1,074.212 seconds
reported by unittest; return code 1). No passing full suite is claimed.

Reported causes include missing native DLLs/modules and packaged resources,
stale or foreign PI/SI and retained-case evidence, absent qualification fixture
paths, and rejected co-simulation runs. These failures remain unresolved; no
claim is made that every failure is environmental or that the source is qualified.
Solver changes are intentionally excluded from this hotfix.

## Release status

Numerical human review is incomplete. Existing provenance gaps and all execution
gates remain open as documented for 0.4.2. The owner authorized experimental
publication with review incomplete; this does not establish physical validation.
The release must remain a prerelease with explicit source-only assets and these
limitations. No installation update is implied.
