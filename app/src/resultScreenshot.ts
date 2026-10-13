// SPDX-License-Identifier: Apache-2.0
/** Bounded, single-frame image export. This is a picture, not a solver dataset. */
export type ResultScreenshotFormat = "webp" | "jpeg" | "png";
export const resultScreenshotFormats = [
  { id: "webp", label: "WebP (compressed)", mime: "image/webp", extension: "webp" },
  { id: "jpeg", label: "JPEG (compressed)", mime: "image/jpeg", extension: "jpg" },
  { id: "png", label: "PNG (lossless)", mime: "image/png", extension: "png" },
] as const;

export async function encodeResultScreenshot(frame: ImageData, format: ResultScreenshotFormat,
  makeCanvas: () => HTMLCanvasElement = () => document.createElement("canvas")): Promise<Blob> {
  const codec = resultScreenshotFormats.find(item => item.id === format);
  if (!codec) throw new Error("Unsupported screenshot format.");
  if (!Number.isInteger(frame.width) || !Number.isInteger(frame.height) || frame.width < 1 || frame.height < 1
    || frame.width * frame.height > 4_000_000) throw new Error("Screenshot exceeds the 4 megapixel limit.");
  const canvas = makeCanvas();
  try {
    canvas.width = frame.width; canvas.height = frame.height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Screenshot encoding is unavailable.");
    context.putImageData(frame, 0, 0);
    const blob = await new Promise<Blob | null>((resolve, reject) => {
      try { canvas.toBlob(resolve, codec.mime, 0.9); } catch (error) { reject(error); }
    });
    if (!blob || !blob.size) throw new Error("Screenshot encoding failed.");
    // Browsers may silently return PNG when a requested encoder is unavailable.
    if (blob.type !== codec.mime) throw new Error(`${codec.label} is unavailable in this runtime. Choose PNG instead.`);
    return blob;
  } finally {
    canvas.width = 0; canvas.height = 0;
  }
}
