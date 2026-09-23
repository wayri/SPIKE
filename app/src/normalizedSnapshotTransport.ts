// SPDX-License-Identifier: MIT
const MAX_SOURCE_BYTES = 512 * 1024 * 1024;
const digestOf = async (bytes: Uint8Array<ArrayBuffer>) => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), value => value.toString(16).padStart(2, "0")).join("");

async function decodeVerifiedText(archive: any, maximumBytes: number): Promise<string> {
  if (!archive
    || !Number.isSafeInteger(archive.bytes) || archive.bytes < 2 || archive.bytes > maximumBytes
    || !/^[a-f0-9]{64}$/.test(archive.sha256) || typeof archive.data !== "string"
    || archive.data.length > maximumBytes) throw new Error("Invalid compressed normalized transport.");
  const compressed = Uint8Array.from(atob(archive.data), character => character.charCodeAt(0));
  const reader = new Blob([compressed]).stream().pipeThrough(new DecompressionStream("deflate")).getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > archive.bytes) throw new Error("Compressed normalized data exceeds their declared size.");
      chunks.push(value);
    }
  } finally { await reader.cancel(); }
  if (length !== archive.bytes) throw new Error("Compressed normalized length mismatch.");
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  const digest = await digestOf(bytes);
  if (digest !== archive.sha256) throw new Error("Compressed normalized checksum mismatch.");
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}

/** Restore exact compressed source/legacy rows; never tessellate solver data. */
export async function hydrateNormalizedSnapshot(input: string | Record<string, unknown>, canonicalDesign?: Record<string, unknown> | null): Promise<string> {
  let source = typeof input === "string" ? input : JSON.stringify(input);
  let snapshot = typeof input === "string" ? JSON.parse(input) : input;
  if (snapshot.contract === "spike/normalized-source-zlib/v1") {
    const needsCanonical = snapshot.canonical_design_omitted === true;
    if (snapshot.encoding !== "zlib+base64+utf8") throw new Error("Unsupported normalized source encoding.");
    source = await decodeVerifiedText(snapshot, MAX_SOURCE_BYTES);
    snapshot = JSON.parse(source);
    if (needsCanonical) {
      if (!canonicalDesign || typeof canonicalDesign !== "object" || Array.isArray(canonicalDesign)) throw new Error("Compact normalized source is missing its canonical design.");
      snapshot.canonical_design = canonicalDesign;
      source = JSON.stringify(snapshot);
    }
  }
  if (snapshot.contract !== "spike/design-snapshot/v1" || snapshot.design?.contract !== "spike/v1") throw new Error("Invalid normalized design snapshot.");
  const projection = snapshot.canonical_design?.metadata?.transport_projection;
  if (!projection?.legacy_omitted_collections?.includes("zones")) return source;
  const archive = projection.legacy_zones_archive;
  if (archive?.encoding !== "zlib+base64+json" || !Number.isSafeInteger(archive.count) || archive.count < 0) throw new Error("Invalid compressed normalized transport.");
  const zones = JSON.parse(await decodeVerifiedText(archive, 128 * 1024 * 1024));
  if (!Array.isArray(zones) || zones.length !== archive.count) throw new Error("Compressed ODB zone count mismatch.");
  snapshot.design.zones = zones;
  projection.legacy_omitted_collections = projection.legacy_omitted_collections.filter((name: string) => name !== "zones");
  return JSON.stringify(snapshot);
}

/** Compact only the transport representation; preserve exact source bytes. */
export async function compressNormalizedSnapshot(source: string): Promise<string> {
  const bytes = new TextEncoder().encode(source);
  if (bytes.length > MAX_SOURCE_BYTES) throw new Error("Normalized source exceeds the 512 MiB decoded limit.");
  const compressed = new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new CompressionStream("deflate"))).arrayBuffer());
  const chunks: string[] = [];
  for (let offset = 0; offset < compressed.length; offset += 16384) chunks.push(String.fromCharCode(...compressed.subarray(offset, offset + 16384)));
  return JSON.stringify({contract:"spike/normalized-source-zlib/v1",encoding:"zlib+base64+utf8",bytes:bytes.length,sha256:await digestOf(bytes),data:btoa(chunks.join(""))});
}
