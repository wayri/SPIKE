import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import BoardImportPanel from '../src/BoardImportPanel';
import type { BoardImportProgress } from '../src/boardImportProgress';

const initial: BoardImportProgress = { fileName: 'JTYU-TSMC-Ki10.kicad_pcb', stage: 'components', percent: 60,
  label: 'Resolving and loading 3D parts', startedAt: Date.now(), busy: true, warnings: [], problems: [] };
function Preview() {
  const [progress, setProgress] = useState(initial);
  const [open, setOpen] = useState(true);
  return <main style={{ background: '#0c171c', color: '#e8f2f3', minHeight: '100vh', fontFamily: 'Arial, sans-serif', padding: 30 }}>
    <h1>Import panel preview</h1><p>Development fixture for the production import panel.</p>
    <button onClick={() => { setProgress({ ...initial, startedAt: Date.now() }); setOpen(true); }}>Show progress</button>{' '}
    <button onClick={() => { setProgress({ ...initial, stage: 'ready', percent: 100, busy: false, label: 'Board imported with items to review',
      problems: [{ source: '${KIPRJMOD}/packages3D/3-122-717.stp', references: ['F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8'] }] }); setOpen(true); }}>Show missing model</button>
    {open && <BoardImportPanel progress={progress} onHide={() => setOpen(false)} onCancel={() => setProgress({ ...progress, busy: false, stage: 'cancelled', label: 'Import stopped; completed geometry is retained' })}
      onRetry={() => setProgress(initial)} onLocate={() => setProgress(initial)} />}
  </main>;
}
createRoot(document.getElementById('root')!).render(<Preview />);
