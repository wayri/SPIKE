# Saved result playback and animation export

The transient result controls play only solver-returned samples. Their Play,
Pause, seek and speed actions never start, pause, resume or stop a solver job.
Solver execution remains in the owning PI, SI, EM or thermal run workspace and
must use the worker's actual cancellation contract.

Playback maps elapsed wall time to each frame's returned `time_s`. It displays
the last saved sample at or before that time and does not interpolate fields or
invent intermediate physics. Playback speed changes review time only. A 2x
setting displays two seconds of simulated time per wall-clock second.

GIF and WebM export use the same saved-time schedule. A bounded export may thin
the frame list, but always retains the first and last solved samples and holds a
retained frame until the next retained sample time. The final sample receives a
short terminal hold. GIF duration is quantized to centiseconds. WebM depends on
the desktop WebView providing `MediaRecorder`,
canvas capture and a VP9, VP8 or generic WebM codec; the UI reports the feature
as unavailable when these are missing.

Default guards limit an export to 180 frames, 60 seconds of encoded playback,
1920 x 1080 pixels, 256 MiB of raw GIF frames, and 256 MiB of retained WebM
chunks. Exports exceeding a guard fail with a recovery message. The user may
increase playback speed, lower dimensions or narrow the saved result. Export is
cancellable and restores the viewport's original saved frame after completion.
The 800 x 500 main and thermal viewport exporters request at most 160 frames so
their worst-case raw GIF capture remains below the 256 MiB guard.

These controls do not create solver frames, establish solver convergence, or
upgrade an approximate or experimental model status. PI, SI, EM and thermal
results remain governed by their solver-specific capability and validity data.

The lumped component thermal overlay uses the same timestamp playback control,
but does not offer animation export because it has no dedicated capture surface.
The assembly thermal volume viewer exports only its own rendered Plotly surface;
it does not capture another open viewport or surrounding controls. Each thermal
frame is a returned nodal sample. Playback and export never interpolate a new
temperature solution between saved times.
