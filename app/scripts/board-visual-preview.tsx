import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import BoardViewport, { type ModelLoadStatus, type RenderTelemetry } from '../src/BoardViewport';
import { parseDesignSourceOffThread } from '../src/boardImport';
import { materializeVisualBundle } from '../src/boardVisualBundles';
import type { ParsedBoard } from '../src/boardParser';
import '../src/styles.css';

const noop = () => {};
const opacity = {};
const assembly = [];
const releases: (() => void)[] = [];
function Preview() {
  const [board, setBoard] = useState<ParsedBoard | null>(null);
  const [mode, setMode] = useState<'2D' | '3D'>('3D');
  const [selectedLayer, setSelectedLayer] = useState('all');
  const [separation, setSeparation] = useState(0);
  const [models, setModels] = useState(true);
  const [netNames, setNetNames] = useState(false);
  const [message, setMessage] = useState('Choose a board and its captured visual stage responses.');
  const [model, setModel] = useState<ModelLoadStatus | null>(null);
  const [telemetry, setTelemetry] = useState<RenderTelemetry | null>(null);
  const visible = useMemo(() => Object.fromEntries((board?.layerDefinitions ?? []).map(layer => [layer.name,
    selectedLayer === 'all' ? !/CrtYd|Fab|Adhes|Margin|User\./.test(layer.name) : layer.name === selectedLayer || layer.name === 'Edge.Cuts'])), [board, selectedLayer]);
  const loadBoard = async (file: File) => {
    try { setMessage('Parsing board'); releases.splice(0).forEach(dispose => dispose());
      const parsed = await parseDesignSourceOffThread(file.name, await file.text()); setBoard(parsed);
      setMessage(`${parsed.components.length} parts · ${parsed.layerDefinitions.length} layers · source geometry ready`);
    } catch (error) { setMessage(String(error)); }
  };
  const loadVisuals = async (files: FileList) => {
    if (!board) return;
    let next = board;
    try {
      for (const file of Array.from(files)) {
        setMessage(`Verifying ${file.name}`);
        const response = JSON.parse(await file.text());
        if (!response.ok) throw new Error(response.error);
        const result = await materializeVisualBundle(next, response.result);
        next = result.board; releases.push(result.dispose); setBoard(next);
      }
      setMessage(`${next.components.length} parts · ${Object.keys(next.layoutLayerUrls ?? {}).length} exported layers · native copper ${next.boardModelIncludesCopper === false}`);
    } catch (error) { setMessage(String(error)); }
  };
  const loadLocal = async () => {
    try {
      setMessage('Loading local regression fixture');
      releases.splice(0).forEach(dispose => dispose());
      const root = '../.tmp/marble-qa/';
      let next = await parseDesignSourceOffThread('Marble.kicad_pcb', await (await fetch(root + 'source.kicad_pcb')).text());
      for (const stage of ['layout', 'board', 'components']) {
        const response = await (await fetch(root + stage + '-response.json')).json();
        const result = await materializeVisualBundle(next, response.result);
        next = result.board; releases.push(result.dispose);
      }
      setBoard(next);
      setMessage(`${next.components.length} parts · ${Object.keys(next.layoutLayerUrls ?? {}).length} exported layers · native copper ${next.boardModelIncludesCopper === false}`);
    } catch (error) { setMessage(String(error)); }
  };
  return <main style={{ height: '100vh', display: 'flex', flexDirection: 'column', color: '#dce9ee', background: '#102028' }}>
    <header style={{ padding: 12, display: 'flex', gap: 16, alignItems: 'center' }}>
      <button onClick={() => void loadLocal()}>Load Marble v1.4.4 QA fixture</button>
      <label>Source board <input type="file" accept=".kicad_pcb" onChange={event => { if (event.target.files?.[0]) void loadBoard(event.target.files[0]); }} /></label>
      <label>Visual responses <input type="file" accept=".json" multiple disabled={!board} onChange={event => { if (event.target.files) void loadVisuals(event.target.files); }} /></label>
      <button onClick={() => setMode(mode === '3D' ? '2D' : '3D')}>{mode === '3D' ? 'Show 2D' : 'Show 3D'}</button>
      <label>Layer <select value={selectedLayer} onChange={event => setSelectedLayer(event.target.value)}><option value="all">All layers</option>{board?.layerDefinitions.map(layer => <option key={layer.name}>{layer.name}</option>)}</select></label>
      <label><input type="checkbox" checked={netNames} onChange={event => setNetNames(event.target.checked)} />Net names (2D)</label>
      <label><input type="checkbox" checked={models} onChange={event => setModels(event.target.checked)} />3D parts</label>
      <label><input type="checkbox" checked={separation > 0} onChange={event => setSeparation(event.target.checked ? 4 : 0)} />Separate layers</label>
    </header>
    <p style={{ margin: '0 12px 8px' }}>{message}</p>
    <div className={`board-canvas ${mode === '3D' ? 'is-3d' : ''}`} style={{ flex: 1, position: 'relative', minHeight: 0 }}>
      {board && <BoardViewport board={board} viewMode={mode} visibleLayers={visible} layerOpacity={opacity} layerSeparation={separation}
        showVias showNetNames={netNames} showModels={models} showSmdModels showThtModels navigationMode="orbit" navigationInertia cameraCommand="fit:1"
        assemblyModels={assembly} selectionFilter="all" selectedId={null} onSelect={noop} onCamera={noop} onModelStatus={setModel} onTelemetry={setTelemetry} />}
    </div>
    <output style={{ padding: 10 }}>{model ? `Board ${model.board} · Parts ${model.components} · Missing ${model.missingCount} · ${model.metrics} ${model.error ?? ''}` : ''}
      {telemetry ? ` · ${telemetry.drawCalls} draws · ${telemetry.triangles} triangles · ${Math.round(telemetry.fps)} FPS` : ''}</output>
  </main>;
}
createRoot(document.getElementById('root')!).render(<Preview />);
