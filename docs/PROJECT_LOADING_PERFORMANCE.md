# Project loading performance

Project reads use a cancellable exclusive worker slot, including the initial
read/decompress/verify stage. The native default watchdog remains 210 seconds;
classifying a read as heavy does not extend it to the solver default.
Cancellation suppresses late results and terminates the owned worker process.

The desktop requests `compact_canonical_design` alongside compact normalized
source. This opt-in IPC representation compresses the authoritative canonical
IR with zlib, UTF-8 byte length and SHA-256. The frontend bounds decompression
at 512 MiB, verifies length and digest, and restores the exact IR before using
it. Default API clients still receive the ordinary canonical object. This does
not change the saved package format, omit solver geometry or skip validation.

## Diagnostic evidence

The 2,584,346-byte `esp32-demo-input.spike` fixture took 0.254 seconds in the
source package handler, with 0.232 seconds in secure reading. Its original
worker response was 13,780,417 UTF-8 bytes. A separate full child-process check
measured 3.356 seconds for the source worker and 11.214 seconds for the bundled
worker; the bundled handler itself took 0.286 seconds. These timings include
different startup/transport stages and are not interchangeable.

Fast canonical compression reduced the like-for-like compact-JSON response
from 12,995,559 to 8,111,352 bytes (37.584%). It preserves exact canonical,
project and manifest values. Handler plus JSON encoding took 0.435 seconds
versus 0.353 seconds without canonical compression; this small CPU tradeoff
reduces IPC volume, and does not prove an end-to-end loading speedup.

The reported 139-second initial-stage stall was not reproduced. The initial
stage also includes worker startup and transport, so its label does not isolate
ZIP decompression. Cold frozen startup remains a separate optimization target.
Backend profiles exclude frontend parsing, native export and GPU scene creation.
The native cancellation fix takes effect after rebuilding the desktop host;
already installed executables retain their previous behavior.

Verification: 59 focused Python package/protocol checks passed; native Cargo
checks passed (44 tests, one ignored); TypeScript, frontend transport/cancellation,
project/parser and architecture checks passed. The exact ESP32 canonical IR was
also restored in the frontend and compared with an independent Node zlib decode.
The broad Python discovery run was interrupted before completion during resource
pressure; its partial log is not a full-suite pass. Machine-specific detailed
results are in `output/project-loading-*`.

Mesh/Solve layout no longer imposes a 180-pixel setup-panel cap. Controls use their
natural height, summary cards stack below a 600-pixel canvas width, and constrained
windows scroll while retaining viewport space. The sidebar separates its label,
value, description and actions. The rebuilt browser preview verified full action
visibility at normal size, stacked summaries at a 479-pixel panel width, and no
document horizontal overflow. Both Mesh and Solve retained their action rows.
