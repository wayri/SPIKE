// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { Download, Pause, Play, X, ArrowLeft, ArrowRight, RotateCcw } from "./icons";
import { detectWebMCapability, type AnimationExportFormat, type AnimationExportRequest } from "./animationExport";
import { createPlaybackTimeline } from "./transientPlayback";
import "./SavedFramePlaybackControls.css";

type Props = {
  timesS: readonly number[];
  frameIndex: number;
  playing: boolean;
  playbackSpeed: number;
  onFrame: (frameIndex: number) => void;
  onPlaying: (playing: boolean) => void;
  onPlaybackSpeed: (speed: number) => void;
  onExport?: (request: AnimationExportRequest, signal: AbortSignal) => Promise<void> | void;
  exportLabel?: string;
  managedPlayback?: boolean;
};

const SPEEDS = [0.25, 0.5, 1, 2, 4, 10, 25, 100] as const;

export default function SavedFramePlaybackControls({
  timesS, frameIndex, playing, playbackSpeed, onFrame, onPlaying, onPlaybackSpeed, onExport, exportLabel = "viewport", managedPlayback = false,
}: Props) {
  const [format, setFormat] = useState<AnimationExportFormat>("gif");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [loop, setLoop] = useState(false);
  const exportAbort = useRef<AbortController | null>(null);
  const webM = useMemo(() => detectWebMCapability(), []);
  const timeline = useMemo(() => {
    try { return { value: createPlaybackTimeline(timesS), error: "" }; }
    catch (error) { return { value: null, error: error instanceof Error ? error.message : String(error) }; }
  }, [timesS]);
  const boundedFrame = Math.min(Math.max(0, Math.trunc(frameIndex)), Math.max(0, timesS.length - 1));

  useEffect(() => {
    if (managedPlayback || !playing || !timeline.value) return;
    let started = performance.now();
    let startFrame = boundedFrame;
    let request = 0;
    const advance = (now: number) => {
      const state = timeline.value!.frameAtElapsed(startFrame, now - started, playbackSpeed);
      onFrame(state.frameIndex);
      if (state.ended && !loop) onPlaying(false);
      else {
        if (state.ended) { started = now; startFrame = 0; onFrame(0); }
        request = requestAnimationFrame(advance);
      }
    };
    request = requestAnimationFrame(advance);
    return () => cancelAnimationFrame(request);
  }, [managedPlayback, playing, playbackSpeed, timeline.value, loop]);

  useEffect(() => () => exportAbort.current?.abort(), []);

  const beginExport = async () => {
    if (!onExport || exporting) return;
    const controller = new AbortController();
    exportAbort.current = controller;
    setExporting(true);
    setExportError("");
    try {
      await onExport({ format, playbackSpeed }, controller.signal);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) setExportError(error instanceof Error ? error.message : String(error));
    } finally {
      if (exportAbort.current === controller) exportAbort.current = null;
      setExporting(false);
    }
  };

  const canPlay = Boolean(timeline.value) && !timeline.error;
  return <div className="saved-frame-playback" aria-label="Stored result playback">
    <div className="saved-frame-playback__heading">
      <b>STORED RESULT PLAYBACK</b>
      <span>These controls review returned solver samples. They do not run, pause, resume, or stop a solver job.</span>
    </div>
    <div className="saved-frame-playback__controls">
      <button type="button" aria-label="First saved frame" disabled={!canPlay || boundedFrame === 0} onClick={() => { onPlaying(false); onFrame(0); }}><RotateCcw size={14} /></button>
      <button type="button" aria-label="Previous saved frame" disabled={!canPlay || boundedFrame === 0} onClick={() => { onPlaying(false); onFrame(boundedFrame - 1); }}><ArrowLeft size={14} /></button>
      <button type="button" disabled={!canPlay} onClick={() => {
        if (!playing && boundedFrame >= timesS.length - 1) onFrame(0);
        onPlaying(!playing);
      }} title={playing ? "Pause saved-frame playback" : "Play saved solver frames"}>
        {playing ? <Pause size={14} /> : <Play size={14} />} {playing ? "Pause playback" : "Play saved frames"}
      </button>
      <button type="button" aria-label="Next saved frame" disabled={!canPlay || boundedFrame >= timesS.length - 1} onClick={() => { onPlaying(false); onFrame(boundedFrame + 1); }}><ArrowRight size={14} /></button>
      <button type="button" disabled={!canPlay || boundedFrame >= timesS.length - 1} onClick={() => { onPlaying(false); onFrame(timesS.length - 1); }}>Last frame</button>
      <input aria-label="Saved result frame" type="range" min="0" max={Math.max(0, timesS.length - 1)} value={boundedFrame} disabled={!canPlay}
        onChange={event => { onPlaying(false); onFrame(Number(event.target.value)); }} />
      <span className="saved-frame-playback__position">{timesS.length && Number.isFinite(timesS[boundedFrame])
        ? `Saved frame ${boundedFrame + 1}/${timesS.length} · ${Number(timesS[boundedFrame]).toPrecision(6)} s`
        : "Static result"}</span>
      <label>Playback speed<select value={playbackSpeed} disabled={!canPlay} onChange={event => onPlaybackSpeed(Number(event.target.value))}>
        {SPEEDS.map(speed => <option key={speed} value={speed}>{speed}x simulated time</option>)}
      </select></label>
      {!managedPlayback && <label><input type="checkbox" checked={loop} disabled={!canPlay} onChange={event => setLoop(event.target.checked)} /> Loop saved frames</label>}
    </div>
    {onExport && canPlay && <div className="saved-frame-playback__export">
      <label>Export format<select aria-label="Animation export format" value={format} disabled={exporting} onChange={event => setFormat(event.target.value as AnimationExportFormat)}>
        <option value="gif">GIF</option>
        <option value="webm" disabled={!webM.supported}>WebM{webM.supported ? "" : " (unavailable)"}</option>
      </select></label>
      <button type="button" disabled={exporting} onClick={() => void beginExport()}><Download size={14} /> Export {exportLabel}</button>
      {exporting && <button type="button" className="spike-control--danger" onClick={() => exportAbort.current?.abort()}><X size={14} /> Cancel export</button>}
      {!webM.supported && <span title={webM.reason ?? undefined}>WebM unavailable in this WebView; GIF remains available.</span>}
    </div>}
    {timeline.error && <p role="alert">Saved playback unavailable: {timeline.error}</p>}
    {exportError && <p role="alert">Animation export failed: {exportError}</p>}
  </div>;
}
