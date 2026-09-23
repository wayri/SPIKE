import type { ParsedBoard } from './boardParser';
import { materializeVisualBundle, type VisualBundlePayload } from './boardVisualBundles';

type StateReference = { contract: 'spike/state-artifact-reference/v1'; path: string; sha256: string; bytes: number };
type VisualArtifact = { role: string; path?: string; media_type: string; bytes: number; sha256: string; artifact_base64?: string };
export type SavedBoardVisuals = { contract: 'spike/saved-board-visuals/v1'; artifacts: VisualArtifact[];
  view_box: number[]; board_includes_copper: boolean; quality: Record<string, any> };

export async function hydrateProjectArtifacts(project: Record<string, any>, read: (reference: StateReference) => Promise<unknown>,
  progress: (done: number, total: number) => void = () => {}): Promise<Record<string, any>> {
  const references = new Map<string, StateReference>();
  const collect = (value: any) => {
    if (!value || typeof value !== 'object') return;
    if (value.contract === 'spike/state-artifact-reference/v1') {
      if (!/^state\/artifacts\/[a-f0-9]{64}\.json$/.test(value.path) || !/^[a-f0-9]{64}$/.test(value.sha256)
        || !Number.isInteger(value.bytes) || value.bytes <= 0) throw new Error('Invalid saved result artifact reference.');
      const previous = references.get(value.path);
      if (previous && (previous.sha256 !== value.sha256 || previous.bytes !== value.bytes)) throw new Error('Conflicting saved result identities.');
      references.set(value.path, value); return;
    }
    Object.values(value).forEach(collect);
  };
  collect(project);
  const values = new Map<string, unknown>();
  for (const reference of references.values()) {
    progress(values.size, references.size);
    values.set(reference.path, await read(reference));
  }
  const hydrate = (value: any): any => {
    if (!value || typeof value !== 'object') return value;
    if (value.contract === 'spike/state-artifact-reference/v1') return values.get(value.path);
    return Array.isArray(value) ? value.map(hydrate) : Object.fromEntries(Object.entries(value).map(([key, item]) => [key, hydrate(item)]));
  };
  progress(values.size, references.size);
  return hydrate(project);
}

function localVisualUrl(url: string): boolean {
  if (url.startsWith('blob:') || url.startsWith('/') && !url.startsWith('//')) return true;
  try { return new URL(url, location.href).origin === location.origin; } catch { return false; }
}

export async function serializeBoardVisuals(board: ParsedBoard | null,
  progress: (message: string) => void = () => {}): Promise<SavedBoardVisuals | undefined> {
  if (!board) return undefined;
  const sources: [string, string][] = [
    ...(board.boardModelUrl ?? board.fullModelUrl ? [['board', (board.boardModelUrl ?? board.fullModelUrl)!] as [string, string]] : []),
    ...(board.componentModelUrl ? [['components', board.componentModelUrl] as [string, string]] : []),
    ...Object.entries(board.layoutLayerUrls ?? {}).map(([name, url]) => [`layer:${name}`, url] as [string, string]),
  ];
  if (!sources.length) return undefined;
  const artifacts: VisualArtifact[] = [];
  let total = 0;
  for (const [role, url] of sources) {
    if (!localVisualUrl(url)) throw new Error('Project visuals must be loaded locally before saving.');
    progress(`Saving imported visuals ${artifacts.length + 1}/${sources.length}`);
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Could not read the imported ${role} visual for saving.`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    total += bytes.byteLength;
    if (total > 96 * 1024 * 1024) throw new Error('Imported visuals exceed the 96 MiB save transport limit.');
    const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
    let binary = '';
    for (let start = 0; start < bytes.length; start += 32768) binary += String.fromCharCode(...bytes.subarray(start, start + 32768));
    artifacts.push({ role, media_type: role.startsWith('layer:') ? 'image/svg+xml' : 'model/gltf-binary', bytes: bytes.length,
      sha256: [...hash].map(value => value.toString(16).padStart(2, '0')).join(''), artifact_base64: btoa(binary) });
  }
  let quality = {};
  if (board.modelManifestUrl && localVisualUrl(board.modelManifestUrl)) {
    const response = await fetch(board.modelManifestUrl);
    if (response.ok) quality = (await response.json()).quality ?? {};
  }
  return { contract: 'spike/saved-board-visuals/v1', artifacts, quality,
    view_box: board.layoutViewBox ?? [], board_includes_copper: board.boardModelIncludesCopper !== false };
}

function assertSelfContainedArtifact(artifact: VisualArtifact) {
  if (!Number.isInteger(artifact.bytes) || artifact.bytes < 1 || artifact.bytes > 96 * 1024 * 1024
    || !/^[a-f0-9]{64}$/.test(artifact.sha256) || typeof artifact.artifact_base64 !== 'string'
    || artifact.artifact_base64.length > Math.ceil(artifact.bytes / 3) * 4) throw new Error('Invalid saved visual artifact metadata.');
  const binary = atob(artifact.artifact_base64!);
  if (artifact.role.startsWith('layer:')) {
    if (!/<svg\b/i.test(binary) || /<script\b|<foreignObject\b|\son\w+\s*=|\bhref\s*=\s*["'](?!#|data:)/i.test(binary)) {
      throw new Error('Saved layer contains unsupported active or external SVG content.');
    }
    return;
  }
  const bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
  const view = new DataView(bytes.buffer);
  if (bytes.length < 20 || view.getUint32(0, true) !== 0x46546c67 || view.getUint32(4, true) !== 2 || view.getUint32(8, true) !== bytes.length) {
    throw new Error('Saved model is not a valid GLB.');
  }
  const jsonBytes = view.getUint32(12, true);
  if (view.getUint32(16, true) !== 0x4e4f534a || 20 + jsonBytes > bytes.length) throw new Error('Saved GLB has no valid JSON chunk.');
  const gltf = JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + jsonBytes)));
  if ([...(gltf.buffers ?? []), ...(gltf.images ?? [])].some(item => item.uri && !String(item.uri).startsWith('data:'))) {
    throw new Error('Saved GLB references an external resource.');
  }
}

/** Native packages read each stage separately; portable JSON carries encoded artifacts. */
export async function restoreBoardVisuals(board: ParsedBoard, saved: SavedBoardVisuals,
  readStage?: (stage: 'layout' | 'board' | 'components') => Promise<unknown>,
  progress: (message: string) => void = () => {}): Promise<{ board: ParsedBoard; dispose: () => void }> {
  if (saved.contract !== 'spike/saved-board-visuals/v1' || !Array.isArray(saved.artifacts)) throw new Error('Invalid saved visual index.');
  const disposers: (() => void)[] = [];
  let next = board;
  try {
    for (const stage of ['layout', 'board', 'components'] as const) {
      const entries = saved.artifacts.filter(item => stage === 'layout' ? item.role.startsWith('layer:') : item.role === stage);
      if (!entries.length) continue;
      progress(`Restoring saved ${stage === 'layout' ? '2D layers' : stage === 'board' ? '3D board' : '3D parts'}`);
      let raw: unknown;
      if (entries.every(entry => typeof entry.artifact_base64 === 'string')) {
        if (entries.reduce((sum, item) => sum + item.bytes, 0) > 96 * 1024 * 1024) throw new Error('Saved visual stage exceeds its byte limit.');
        entries.forEach(assertSelfContainedArtifact);
        const artifacts = entries.map(entry => [entry.role, { ...entry, artifact_base64: entry.artifact_base64!, file_name: entry.role.replace(':', '-') }] as const);
        raw = { contract: 'spike/visual-bundle-payload/v1', status: 'ready',
          scenes: Object.fromEntries(artifacts.filter(([role]) => !role.startsWith('layer:'))),
          layout: { layers: Object.fromEntries(artifacts.filter(([role]) => role.startsWith('layer:')).map(([role, value]) => [role.slice(6), value])), view_box: saved.view_box },
          quality: { ...saved.quality, board_includes_copper: saved.board_includes_copper },
          artifact_bytes: entries.reduce((sum, item) => sum + item.bytes, 0), artifact_limit_bytes: 96 * 1024 * 1024,
          security: { self_contained_glb_required: true, external_resource_uris_allowed: false } } satisfies VisualBundlePayload;
      } else {
        if (!readStage) throw new Error('The original .spike package is required to restore its visual artifacts.');
        raw = await readStage(stage);
      }
      const result = await materializeVisualBundle(next, raw);
      next = result.board; disposers.push(result.dispose);
    }
    return { board: next, dispose: () => disposers.splice(0).forEach(dispose => dispose()) };
  } catch (error) { disposers.forEach(dispose => dispose()); throw error; }
}
