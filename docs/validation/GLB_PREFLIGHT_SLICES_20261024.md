# Portable visual loading: bounded GLB preflight copies

The portable-project visual preflight copied the entire decoded GLB into a
typed array even though it reads only the first 20 bytes and the JSON chunk.
It now copies exactly those slices. `atob` still processes the complete input;
this change does not claim to eliminate its string allocation or decode cost.

Metadata and transport limits, GLB magic/version/total-length checks, JSON chunk
type/bounds, UTF-8 decoding, JSON parsing and external buffer/image URI rejection
are unchanged. The following visual materializer still decodes every payload
byte, checks its length and SHA-256, and only then creates object URLs. SVG
validation, copper policy, disposal and all solver/capability gates are unchanged.
No numerical method or result precision changed.

## Executed evidence

`app/scripts/test-project-visual-byte-conversion.mjs` verifies exact header and
JSON bytes, full materialized payload equality containing all 256 byte values,
and rejection of a changed BIN-only byte at the later SHA-256 gate. It also
checks short/header/version/length/chunk-type/chunk-bounds failures, invalid
base64, bad metadata and external URIs. Existing project-persistence and visual
bundle suites passed, as did TypeScript. Independent review found no actionable
issue; browser/native worker execution and the full 96 MiB limit were not exercised.

Five separate Node v24.14.0 processes each ran seven alternating pairs of three
preflight calls on the same synthetic 131,164-byte GLB. Median of process medians:

| Metric | Previous | Updated |
| --- | ---: | ---: |
| CPU time | 0.24523 ms | 0.08083 ms |
| Range of process medians | 0.21093–0.27283 ms | 0.07197–0.09557 ms |
| Preflight typed-array storage | 131,164 bytes | 84 bytes |

The bounded CPU ratio was 3.03x. The allocation figure covers only preflight's
typed arrays, not the complete project, model, base64 string, renderer or worker.
These results are not measured native project-opening or playback timings.
Raw before-source, five samples, summary and source hashes are under
`output/performance-20261024/glb-preflight-slices/`.

## Playback candidate and native status

A separate bounded playback experiment compared the existing immutable object
spread with a schema-specific sample copier across 30,000 rich samples and ten
uncached frames. In all five processes the candidate was slower: 41.85–54.28 ms
versus 8.64–28.00 ms, with identical checksum 300046.4955. It was fully reverted;
no playback source/test change from that experiment remains. Evidence:
`output/performance-20261024/result-frame-materialization-negative/README.md`.
Post-revert result-performance and TypeScript checks passed. Broader GPU-buffer
lifecycle changes need native profiling and exact mapping/disposal validation.

The current sealed native benchmark build remains
`output/native-release-playback-20261024/target/release/spike-desktop.exe`, SHA-256
`6a7408a75357e458d4461b4545064e5d2e23cd44bac66ea992388c82c29b1770`.
This later loading source change is **not embedded in that executable**. Do not
overwrite its source/frontend/resources or enable hot reload during measurements.
Keep new-source evidence separate until another native build is sealed. The
live checkout has concurrent version/capability work; it was not reset or
silently substituted for the qualified benchmark snapshot.

At the start of this continuation, Windows CIM reported 3,026,300,928 free bytes,
below the 6,000,000,000-byte native board-workload gate. No native board-load or
responsiveness stress workload was started below that gate. Native checks and
10/20-board measurements on the rebuilt release remain pending a fresh successful
gate. The operational gate does not establish a hard memory limit or the separate
16 GB installed/10 GB available qualification target. Missing White Rabbit/server
inputs and unresolved Marble models retain their existing status.

## Native attempt and remaining blockers

At 13:46:59 UTC the free-RAM gate reached 6,381,572,096 bytes. The sealed native
launcher checked again at 13:47:36 UTC (6,041,772,032 bytes) before starting a
fresh task-owned empty app. The required post-startup gate then fell to
4,056,444,928 bytes; no board was loaded. Supported Computer Use subsequently
showed the Windows lock screen, so desktop inputs stopped immediately and the
human was asked to unlock. The empty task-owned app remains running; concurrent
debug and installed instances were left untouched. Fresh identity verification
is required before reusing the app, not reliance on its recorded PID alone.

Evidence is under
`output/native-release-playback-20261024/native-board-bench-20261024-evening/`.
Its 30-second idle-only trace contains 18 samples with peaks of 586,768,384
private bytes and 868,171,776 aggregate working-set bytes across seven host/
WebView processes, plus separate shared GPU usage of 415,313,920 bytes and zero
dedicated GPU usage. These counters overlap and must not be added. No worker was
observed in this empty-host trace. Concurrent system activity prevents
attributing the whole-host RAM drop solely to this app. This is not a board
benchmark, measured dense playback FPS, repeated-reopen plateau or hard-limit
qualification. The temporary monitor now records the lock/RAM blockers and
the already-running task-owned instance to avoid duplicate launches.

The current checkout's required architecture command was executed and failed
on concurrent `app/src-tauri/tauri.conf.json` entries missing `../../python/core`,
`../../python/spike_core` and `../../extensions`. This is the previously recorded
live/frozen configuration distinction. Neither that configuration nor its guard
was changed. The sealed benchmark snapshot's architecture check passed earlier;
that does not establish that this later source-only loading change has passed a
new frozen build or native acceptance.
