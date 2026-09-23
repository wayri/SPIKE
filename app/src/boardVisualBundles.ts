import type { ParsedBoard } from "./boardParser";

type EncodedArtifact = {
  file_name: string;
  media_type: string;
  bytes: number;
  sha256: string;
  artifact_base64: string;
};

export type VisualBundlePayload = {
  contract: "spike/visual-bundle-payload/v1";
  status: string;
  scenes: { board?: EncodedArtifact; components?: EncodedArtifact };
  layout: { layers: Record<string, EncodedArtifact>; view_box: number[] };
  quality: { missing_model_count?: number; missing_references?: string[]; unresolved_model_paths?: string[]; board_includes_copper?: boolean };
  artifact_bytes: number;
  artifact_limit_bytes: number;
  security: { self_contained_glb_required: true; external_resource_uris_allowed: false };
};

export type MaterializedVisualBundle = {
  board: ParsedBoard;
  dispose: () => void;
  missingReferences: string[];
};

const MAX_VISUAL_BUNDLE_BYTES = 96 * 1024 * 1024;

function encodedArtifacts(payload: VisualBundlePayload): [string, EncodedArtifact][] {
  return [
    ...Object.entries(payload.scenes).map(([name, artifact]) => [name, artifact] as [string, EncodedArtifact]),
    ...Object.entries(payload.layout.layers).map(([layer, artifact]) => [`layer:${layer}`, artifact] as [string, EncodedArtifact]),
  ];
}

function decodeBase64(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}

type DecodedArtifact = { buffer: ArrayBuffer; sha256: string };

async function sha256(buffer: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, "0")).join("");
}

const KICAD_SVG11_PUBLIC_DECLARATION = /^(\s*(?:<\?xml\s[^?]*\?>\s*)?)<!DOCTYPE svg PUBLIC "-\/\/W3C\/\/DTD SVG 1\.1\/\/EN"\s+"http:\/\/www\.w3\.org\/Graphics\/SVG\/1\.1\/DTD\/svg11\.dtd">\s*/i;

/** SVG layer artifacts are rendered from object URLs, so retain the same
 * active/external-content boundary regardless of how the package was read.
 * KiCad's inert SVG 1.1 public DTD is removed only from the render buffer;
 * integrity remains checked against the original package bytes. */
function safeSvgRenderBuffer(buffer: ArrayBuffer): ArrayBuffer {
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(buffer);
  } catch {
    throw new Error("Saved layer is not valid UTF-8 SVG.");
  }
  const normalized = text.replace(KICAD_SVG11_PUBLIC_DECLARATION, "$1");
  const safeReference = (value: string) => value.startsWith("#")
    || /^data:image\/(?:png|jpeg|gif|webp|avif)(?:;base64)?,/i.test(value);
  const references = [
    ...normalized.matchAll(/\b(?:xlink:)?href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/gi),
    ...normalized.matchAll(/\burl\(\s*(?:"([^"]*)"|'([^']*)'|([^\s)]+))\s*\)/gi),
  ];
  const hasUnsafeReference = references.some(match => !safeReference((match[1] ?? match[2] ?? match[3] ?? "").trim()));
  const css = [...normalized.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style\s*>|\bstyle\s*=\s*(?:"([^"]*)"|'([^']*)')/gi)]
    .map(match => match[1] ?? match[2] ?? match[3] ?? "");
  const hasObfuscatedExternalCss = css.some(value => {
    const unescaped = value.replace(/\\([0-9a-f]{1,6}\s?|.)/gi, (_match, escape) => {
      const hex = String(escape).trim();
      return /^[0-9a-f]{1,6}$/i.test(hex) ? String.fromCodePoint(Number.parseInt(hex, 16)) : escape;
    });
    return unescaped !== value && /@import\b|url\s*\(/i.test(unescaped);
  });
  if (!/<svg\b/i.test(normalized)
    || /<!DOCTYPE\b|<!ENTITY\b|<\?xml-stylesheet\b|@import\b|<script\b|<foreignObject\b|\bon\w+\s*=/i.test(normalized)
    || hasUnsafeReference || hasObfuscatedExternalCss) {
    throw new Error("Saved layer contains unsupported active or external SVG content.");
  }
  return new TextEncoder().encode(normalized).buffer;
}

async function decodeArtifactsOffThread(artifacts: [string, EncodedArtifact][]): Promise<Map<string, DecodedArtifact>> {
  if (typeof Worker === "undefined") {
    const decoded = await Promise.all(artifacts.map(async ([id, artifact]) => {
      const buffer = decodeBase64(artifact.artifact_base64);
      return [id, { buffer, sha256: await sha256(buffer) }] as const;
    }));
    return new Map(decoded);
  }
  const worker = new Worker(new URL("./visualBundleDecodeWorker.ts", import.meta.url), { type: "module" });
  try {
    return await new Promise<Map<string, DecodedArtifact>>((resolve, reject) => {
      const timeout = window.setTimeout(() => reject(new Error("Visual bundle decoding exceeded 120 seconds.")), 120_000);
      worker.onmessage = event => {
        window.clearTimeout(timeout);
        const items = Array.isArray(event.data?.items) ? event.data.items as { id: string; buffer: ArrayBuffer; sha256: string }[] : [];
        resolve(new Map(items.map(item => [item.id, { buffer: item.buffer, sha256: item.sha256 }])));
      };
      worker.onerror = event => {
        window.clearTimeout(timeout);
        reject(new Error(event.message || "Visual bundle decoding failed."));
      };
      worker.postMessage({ artifacts: artifacts.map(([id, artifact]) => ({ id, base64: artifact.artifact_base64 })) });
    });
  } finally {
    worker.terminate();
  }
}

export async function materializeVisualBundle(
  source: ParsedBoard,
  raw: unknown,
  objectUrl: (blob: Blob) => string = blob => URL.createObjectURL(blob),
  revokeUrl: (url: string) => void = url => URL.revokeObjectURL(url),
): Promise<MaterializedVisualBundle> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("Visual worker returned no bundle payload.");
  const payload = raw as VisualBundlePayload;
  if (payload.contract !== "spike/visual-bundle-payload/v1") throw new Error("Visual worker returned an unsupported bundle contract.");
  if (payload.security?.self_contained_glb_required !== true || payload.security?.external_resource_uris_allowed !== false) {
    throw new Error("Visual bundle did not preserve the self-contained GLB security boundary.");
  }
  if (!Number.isInteger(payload.artifact_bytes) || payload.artifact_bytes < 1 || payload.artifact_bytes > MAX_VISUAL_BUNDLE_BYTES
    || !Number.isInteger(payload.artifact_limit_bytes) || payload.artifact_bytes > payload.artifact_limit_bytes) {
    throw new Error("Visual bundle violates the desktop byte budget.");
  }
  const artifacts = encodedArtifacts(payload);
  if (artifacts.length > 256) throw new Error("Visual bundle contains too many display artifacts.");
  const declaredBytes = artifacts.reduce((total, [, artifact]) => {
    if (!artifact || !Number.isInteger(artifact.bytes) || artifact.bytes < 1 || artifact.bytes > MAX_VISUAL_BUNDLE_BYTES
      || !/^[0-9a-f]{64}$/.test(artifact.sha256) || typeof artifact.artifact_base64 !== "string") {
      throw new Error("Visual bundle contains malformed artifact metadata.");
    }
    return total + artifact.bytes;
  }, 0);
  if (declaredBytes !== payload.artifact_bytes) throw new Error("Visual bundle byte accounting does not match its artifacts.");
  const decoded = await decodeArtifactsOffThread(artifacts);
  const urls: string[] = [];
  const urlFor = (id: string, artifact: EncodedArtifact) => {
    const decodedArtifact = decoded.get(id);
    if (!decodedArtifact || decodedArtifact.buffer.byteLength !== artifact.bytes) throw new Error(`Visual bundle artifact ${id} failed length verification.`);
    if (decodedArtifact.sha256 !== artifact.sha256) throw new Error(`Visual bundle artifact ${id} failed SHA-256 verification.`);
    const renderBuffer = id.startsWith("layer:") ? safeSvgRenderBuffer(decodedArtifact.buffer) : decodedArtifact.buffer;
    const url = objectUrl(new Blob([renderBuffer], { type: artifact.media_type }));
    urls.push(url);
    return url;
  };
  try {
    const board: ParsedBoard = {
      ...source,
      fullModelUrl: undefined,
      boardModelUrl: payload.scenes.board ? urlFor("board", payload.scenes.board) : source.boardModelUrl,
      boardModelIncludesCopper: payload.scenes.board ? payload.quality?.board_includes_copper !== false : source.boardModelIncludesCopper,
      componentModelUrl: payload.scenes.components ? urlFor("components", payload.scenes.components) : source.componentModelUrl,
      layoutLayerUrls: { ...source.layoutLayerUrls, ...Object.fromEntries(Object.entries(payload.layout.layers).map(([layer, artifact]) => [
        layer, urlFor(`layer:${layer}`, artifact),
      ])) },
      layoutViewBox: payload.layout.view_box.length === 4 && payload.layout.view_box.every(Number.isFinite)
        ? payload.layout.view_box as [number, number, number, number]
        : source.layoutViewBox,
    };
    const missingReferences = Array.isArray(payload.quality?.missing_references)
      ? payload.quality.missing_references.filter(value => typeof value === "string").slice(0, 10_000)
      : [];
    const manifest = JSON.stringify({
      contract: "spike/scene-manifest/v1",
      status: missingReferences.length ? "ready_with_warnings" : "ready",
      quality: { missing_model_count: missingReferences.length, missing_references: missingReferences },
    });
    if (payload.scenes.components) {
      board.modelManifestUrl = objectUrl(new Blob([manifest], { type: "application/json" }));
      urls.push(board.modelManifestUrl);
    }
    let disposed = false;
    return {
      board,
      missingReferences,
      dispose: () => {
        if (disposed) return;
        disposed = true;
        urls.forEach(revokeUrl);
      },
    };
  } catch (error) {
    urls.forEach(revokeUrl);
    throw error;
  }
}

export function configureBundledVisuals(board: ParsedBoard, demo: "ebrake1" | "modular-bus-nib") {
  if (demo === "modular-bus-nib") {
    const root = "/demo/models/modular-bus-nib";
    board.boardModelUrl = `${root}/MODULAR-BUS-NIB_board.glb`;
    board.componentModelUrl = `${root}/MODULAR-BUS-NIB_components.glb`;
    board.layoutLayerUrls = Object.fromEntries(board.layerDefinitions.map(({ name }) => [
      name,
      `${root}/layout/MODULAR-BUS-NIB-${name.replace(/\./g, "_")}.svg`,
    ]));
    board.layoutViewBox = [0, 0, 45.9994, 30.988];
    board.modelManifestUrl = `${root}/scene.json`;
    return;
  }
  board.fullModelUrl = "/demo/models/ebrake1_fused.glb";
  board.boardModelUrl = "/demo/models/ebrake1_board.glb";
  board.componentModelUrl = "/demo/models/ebrake1_components.glb";
  board.layoutLayerUrls = {
    "F.Cu": "/demo/models/layout/ebrake1-F_Cu.svg",
    "In1.Cu": "/demo/models/layout/ebrake1-In1_Cu.svg",
    "In2.Cu": "/demo/models/layout/ebrake1-In2_Cu.svg",
    "B.Cu": "/demo/models/layout/ebrake1-B_Cu.svg",
    "F.SilkS": "/demo/models/layout/ebrake1-F_Silkscreen.svg",
    "B.SilkS": "/demo/models/layout/ebrake1-B_Silkscreen.svg",
  };
  board.layoutViewBox = [0, 0, 143.9418, 83.4390];
  board.modelManifestUrl = "/demo/models/ebrake1_scene.json";
}

export async function configureKnownVisuals(board: ParsedBoard, sourceFile: string, source?: string) {
  const name = sourceFile.replace(/\\/g, "/").split("/").pop()?.toLowerCase() ?? "";
  const hashes: Record<string, string> = {
    "ebrake1.kicad_pcb": "d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca",
    "modular-bus-nib.kicad_pcb": "37639b58aa75c11265ecf7867c2d358942b70c9e0011a10da99f524e767c2f07",
  };
  // A familiar filename is not evidence that the board still matches a demo.
  if (!source || !hashes[name] || await sha256(new TextEncoder().encode(source).buffer) !== hashes[name]) return false;
  if (name === "ebrake1.kicad_pcb") {
    configureBundledVisuals(board, "ebrake1");
    return true;
  }
  if (name === "modular-bus-nib.kicad_pcb") {
    configureBundledVisuals(board, "modular-bus-nib");
    return true;
  }
  return false;
}
