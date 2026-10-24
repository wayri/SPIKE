// SPDX-License-Identifier: Apache-2.0
import type { AssistantAttachment } from "./assistantConversation";

export const ASSISTANT_ATTACHMENT_ACCEPT = ".png,.jpg,.jpeg,.webp,.txt,.md,.csv,.json,.log,.py,.spice,.cir,.net";
const imageTypes = new Set(["image/png", "image/jpeg", "image/webp"]);
const textExtensions = /\.(txt|md|csv|json|log|py|spice|cir|net)$/i;
export function attachmentBytes(item: AssistantAttachment): number {
  const encoded = item.dataUrl.slice(item.dataUrl.indexOf(",") + 1);
  return Math.floor(encoded.length * 3 / 4) - (encoded.endsWith("==") ? 2 : encoded.endsWith("=") ? 1 : 0);
}
export function checkAttachmentBudget(items: readonly AssistantAttachment[]) {
  if (items.length > 8) throw new Error("A conversation can contain up to 8 attachments. Start a new chat for more.");
  if (items.filter(item => imageTypes.has(item.mimeType)).length > 4) throw new Error("A conversation can contain up to 4 images. Start a new chat for more.");
  if (items.reduce((sum, item) => sum + attachmentBytes(item), 0) > 20 * 1024 * 1024) throw new Error("Attachments exceed the 20 MiB conversation budget.");
}
export async function readAssistantAttachment(file: File): Promise<AssistantAttachment> {
  const mimeType = imageTypes.has(file.type) ? file.type : textExtensions.test(file.name) ? "text/plain" : "";
  if (!mimeType) throw new Error(`${file.name}: use PNG, JPEG, WebP or a UTF-8 text file. Audio, video, PDF and CAD files are not supported in chat yet.`);
  const limit = mimeType === "text/plain" ? 256 * 1024 : 5 * 1024 * 1024;
  if (!file.size || file.size > limit) throw new Error(`${file.name}: file must be nonempty and under ${mimeType === "text/plain" ? "256 KiB" : "5 MiB"}.`);
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (mimeType === "text/plain") {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    if (text.includes("\0")) throw new Error(`${file.name}: binary content is not accepted as text.`);
  } else {
    const png = bytes[0] === 137 && bytes[1] === 80 && bytes[2] === 78 && bytes[3] === 71 && bytes[4] === 13 && bytes[5] === 10 && bytes[6] === 26 && bytes[7] === 10;
    const jpeg = bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255;
    const webp = String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" && String.fromCharCode(...bytes.slice(8, 12)) === "WEBP";
    if (!(mimeType === "image/png" ? png : mimeType === "image/jpeg" ? jpeg : webp)) throw new Error(`${file.name}: image content does not match its type.`);
  }
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return { id: crypto.randomUUID(), name: file.name.replace(/[\\/\u0000-\u001f]/g, "_").slice(0, 180), mimeType,
    dataUrl: `data:${mimeType};base64,${btoa(binary)}`, sha256: Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("") };
}
