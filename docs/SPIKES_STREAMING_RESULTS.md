# SPIKES bounded streaming results

Continuous simulation must not imply recording every value forever. SPIKES
uses three distinct retention policies that share one explicit uniform-stream
schema:

1. `RollingSampleBuffer` retains only the newest configured number of frames.
   Old frames are overwritten and counted; memory use is fixed after admission.
2. `EventCaptureEngine` retains a small pre-trigger ring and emits finite
   pre/post-trigger records. It supports rising, falling, or either-edge
   triggers, hysteresis, holdoff, bounded event queues, explicit drop counters,
   and manual markers from users, limit/SOA monitors, or solver events.
3. `ChunkedWaveformWriter` is for selected longer records. It writes
   independently decodable, CRC-protected chunks with a hard file-byte limit.
   A reader can recover every complete chunk when a run is interrupted before
   the completion marker.

The Python `SessionCaptureMonitor` connects these policies to persistent
soft-real-time sessions. File writes and compression must remain outside a
future hard-real-time solver callback; the deadline thread should only copy
frames into a preallocated bounded transport.

## File format and compression

The experimental `.spkw` format is `spikes/chunked-waveform/v1`. Its JSON
header records channels, SI units, fixed sample interval, time origin, source
digest, codec, and lossless status. Each binary chunk records its absolute
first sample index, sample count, raw/stored byte counts, and CRC32. Chunks reset
their predictor state, so damage to one tail does not make all preceding data
unreadable.

Supported codecs are:

- `none`: raw interleaved IEEE-754 binary64;
- `zlib-fast`: low-latency compression candidate;
- `zlib`: general compression;
- `xor-zlib`: lossless per-channel IEEE-754 XOR prediction followed by zlib;
- `lzma`: offline size-oriented compression candidate.

No codec quantizes values. `compare_codecs` reports deterministic stored sizes
without pretending that desktop timing is a WCET qualification. On one
deterministic 10,000-frame, three-channel switching/ramp/thermal fixture, the
240,000 raw bytes produced these illustrative sizes:

| Codec | Stored bytes | Raw/stored ratio |
|---|---:|---:|
| none | 240,000 | 1.00 |
| zlib-fast | 83,566 | 2.87 |
| zlib | 74,589 | 3.22 |
| xor-zlib | 54,457 | 4.41 |
| lzma | 24,784 | 9.68 |

These ratios are not universal. Switching edges, noise, chaotic states, and
already-compressed data can reduce compression. `xor-zlib` is the current
streaming default; target-hardware throughput tests are required before any
real-time claim. LZMA is intended for offline compaction unless qualified.

## Size policy

Raw binary64 growth is `channels * sample_rate * 8` bytes per second before
metadata. For example, 32 channels at 1 MS/s produce 256 MB/s, so compression
alone cannot make indefinite logging safe. The intended policy is:

- keep a short rolling overview for plots and meters;
- persist only triggered faults, switching anomalies, limit crossings, user
  markers, or explicitly requested intervals;
- use independent chunks for bounded long captures;
- enforce byte, sample, event-count, and queue limits before a run starts;
- report overwritten samples, dropped events, incomplete captures, and torn
  tails instead of hiding them.

Current limitations: the implementation is a Python reference path, uses a
uniform sample clock, and does not yet provide asynchronous disk workers,
multi-rate channel groups, min/max visualization pyramids, rotating archives,
or a native lock-free ring. Those are required before hard-HIL qualification.
