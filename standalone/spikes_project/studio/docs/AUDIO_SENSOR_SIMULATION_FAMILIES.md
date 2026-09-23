# Audio, mechanical sensors and simulation families

## Implemented recorded input

File → Import audio sensor accepts integer PCM WAV (8/16/24/32 bit) or CSV with a `time_s,<signal>,...` header. Select a channel, existing independent V/I source, gain, offset and input-unit label. The resulting PWL source runs in native simulation time; import is undoable. File hash and scaling metadata remain in the schematic. No physical device is opened.

WAV amplitude is normalized full scale, not calibrated pascals. For a virtual accelerometer, CSV values can represent m/s² and gain can represent V/(m/s²). This is an electrical input mapping, not a solved mechanical sensor model. Time must start at zero and increase strictly. Linear interpolation holds the final value after the recording ends. There is no repeat, auto-resampling or silent decimation. Current limits: 16 MiB and 20000 samples. Choose solver timestep based on bandwidth; a large timestep can miss signal detail.

## Monte Carlo today

`python.spikes.sweeps.run_monte_carlo(..., native_library=path)` optionally solves each case in owned C++; omitting it retains the existing reference path. Seeded independent relative variations support uniform or clipped-normal distributions on admitted linear components. This is not full process/mismatch simulation. Existing temperature/corner APIs and `.step` functionality have their own bounded support and are not extended by this change.

## Required next stages — not implemented or qualified

- Explicit microphone/speaker device discovery and opt-in start/stop. No automatic recording, playback or microphone permission on project load.
- Bounded full-duplex rings, timestamp/clock-drift handling, resampling, clipping/underflow/overflow reporting, output gain limits and emergency mute. Best-effort audio is distinct from hard-real-time HIL.
- WAV output and selected-trace audition with calibrated amplitude, explicit sample rate and anti-alias filtering; playback must be user-triggered.
- Transducer/motor/mechanical coupling with displacement, velocity, acceleration, force, pressure and temperature units; calibrated sensor sensitivity, bandwidth, noise, saturation and delay.
- Long-recording streaming and event capture without expanding entire audio tracks into PWL netlists.
- Monte Carlo GUI coordination, correlated process/mismatch variables, additional distributions, Latin-hypercube/quasi-random sampling, confidence intervals, yield and worst-case search, interruption/resume and run provenance.
- Family-wide qualification for DC, AC, transient, noise, transfer/pole-zero, sensitivity, distortion, Fourier, periodic steady state, temperature and corners. Existing features must retain explicit model/analysis restrictions; do not claim complete SPICE parity.
