/// <reference lib="webworker" />

type DecodeRequest = { artifacts: { id: string; base64: string }[] };

self.onmessage = async (event: MessageEvent<DecodeRequest>) => {
  const artifacts = Array.isArray(event.data?.artifacts) ? event.data.artifacts : [];
  const items = await Promise.all(artifacts.map(async artifact => {
    const binary = atob(artifact.base64);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    const sha256 = [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, "0")).join("");
    return { id: artifact.id, buffer: bytes.buffer, sha256 };
  }));
  self.postMessage({ items }, { transfer: items.map(item => item.buffer) });
};

export {};
