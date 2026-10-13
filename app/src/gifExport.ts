const bytes = (...values: number[]) => Uint8Array.from(values, value => value & 0xff);

function palette332() {
  const output = new Uint8Array(256 * 3);
  for (let index = 0; index < 256; index += 1) {
    output[index * 3] = Math.round(((index >> 5) & 7) * 255 / 7);
    output[index * 3 + 1] = Math.round(((index >> 2) & 7) * 255 / 7);
    output[index * 3 + 2] = Math.round((index & 3) * 255 / 3);
  }
  return output;
}

function indexedPixels(image: ImageData) {
  const output = new Uint8Array(image.width * image.height);
  for (let source = 0, target = 0; source < image.data.length; source += 4, target += 1) {
    output[target] = (image.data[source] >> 5) << 5
      | (image.data[source + 1] >> 5) << 2
      | image.data[source + 2] >> 6;
  }
  return output;
}

function lzwEncode(indices: Uint8Array) {
  const clear = 256;
  const end = 257;
  let codeSize = 9;
  let nextCode = 258;
  let dictionary = new Map<string, number>();
  let packed = new Uint8Array(Math.max(16, indices.length * 2 + 16));
  let packedLength = 0;
  let bitBuffer = 0;
  let bitCount = 0;
  const emit = (code: number) => {
    bitBuffer |= code << bitCount;
    bitCount += codeSize;
    while (bitCount >= 8) {
      if (packedLength >= packed.length) {
        const grown = new Uint8Array(packed.length * 2);
        grown.set(packed); packed = grown;
      }
      packed[packedLength++] = bitBuffer & 0xff;
      bitBuffer >>>= 8;
      bitCount -= 8;
    }
  };
  const reset = () => {
    dictionary = new Map();
    codeSize = 9;
    nextCode = 258;
  };
  emit(clear);
  if (!indices.length) {
    emit(end);
  } else {
    let prefix = indices[0];
    for (let index = 1; index < indices.length; index += 1) {
      const suffix = indices[index];
      const key = `${prefix},${suffix}`;
      const known = dictionary.get(key);
      if (known !== undefined) {
        prefix = known;
        continue;
      }
      emit(prefix);
      if (nextCode < 4096) {
        dictionary.set(key, nextCode);
        nextCode += 1;
        if (nextCode === 1 << codeSize && codeSize < 12) codeSize += 1;
      } else {
        emit(clear);
        reset();
      }
      prefix = suffix;
    }
    emit(prefix);
    emit(end);
  }
  if (bitCount > 0) packed[packedLength++] = bitBuffer & 0xff;
  return packed.slice(0, packedLength);
}

export function encodeGif(frames: ImageData[], delayCentiseconds: number | readonly number[]) {
  if (!frames.length) throw new Error("No viewport frames were captured.");
  if (Array.isArray(delayCentiseconds) && delayCentiseconds.length !== frames.length) {
    throw new Error("GIF frame delays must match the captured frame count.");
  }
  const { width, height } = frames[0];
  const rawBytes = width * height * 4 * frames.length;
  if (!Number.isFinite(rawBytes) || rawBytes > 256 * 1024 * 1024) throw new Error("GIF input exceeds the 256 MiB raw-frame limit.");
  const output: BlobPart[] = [new TextEncoder().encode("GIF89a"), bytes(width, width >> 8, height, height >> 8, 0xf7, 0, 0),
    palette332(), bytes(0x21, 0xff, 0x0b), new TextEncoder().encode("NETSCAPE2.0"), bytes(0x03, 0x01, 0, 0, 0)];
  frames.forEach((frame, frameIndex) => {
    if (frame.width !== width || frame.height !== height) throw new Error("Captured GIF frames have inconsistent dimensions.");
    const requestedDelay = Array.isArray(delayCentiseconds) ? delayCentiseconds[frameIndex] : delayCentiseconds;
    const frameDelay = Math.max(1, Math.min(65535, Math.round(Number(requestedDelay))));
    if (!Number.isFinite(frameDelay)) throw new Error(`GIF frame ${frameIndex + 1} has an invalid delay.`);
    const compressed = lzwEncode(indexedPixels(frame));
    output.push(bytes(0x21, 0xf9, 0x04, 0x00, frameDelay, frameDelay >> 8, 0x00, 0x00));
    output.push(bytes(0x2c, 0, 0, 0, 0, width, width >> 8, height, height >> 8, 0x00, 0x08));
    const blocks = new Uint8Array(compressed.length + Math.ceil(compressed.length / 255) + 1);
    let target = 0;
    for (let offset = 0; offset < compressed.length; offset += 255) {
      const length = Math.min(255, compressed.length - offset);
      blocks[target++] = length;
      blocks.set(compressed.subarray(offset, offset + length), target);
      target += length;
    }
    blocks[target] = 0;
    output.push(blocks);
  });
  output.push(bytes(0x3b));
  return new Blob(output, { type: "image/gif" });
}

function drawContained(context: CanvasRenderingContext2D, source: CanvasImageSource, sourceWidth: number, sourceHeight: number, width: number, height: number) {
  context.fillStyle = "#0b141a";
  context.fillRect(0, 0, width, height);
  const scale = Math.min(width / sourceWidth, height / sourceHeight);
  const drawWidth = sourceWidth * scale;
  const drawHeight = sourceHeight * scale;
  context.drawImage(source, (width - drawWidth) / 2, (height - drawHeight) / 2, drawWidth, drawHeight);
}

export async function captureViewport(width = 800, height = 500): Promise<ImageData> {
  const output = document.createElement("canvas");
  output.width = width;
  output.height = height;
  const context = output.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("2D capture canvas is unavailable.");
  const webgl = document.querySelector<HTMLCanvasElement>(".board-canvas canvas.three-canvas");
  const layout = document.querySelector<SVGSVGElement>(".board-canvas .layout-active .layout-viewport > svg, .board-canvas .layout-active .assembly-layout-viewport > svg");
  if (layout && getComputedStyle(layout).display !== "none") {
    const clone = layout.cloneNode(true) as SVGSVGElement;
    clone.querySelectorAll("image").forEach(image => {
      const href = image.getAttribute("href");
      if (href) image.setAttribute("href", new URL(href, window.location.href).href);
    });
    const blob = new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    try {
      const image = new Image();
      image.src = url;
      await image.decode();
      drawContained(context, image, image.width, image.height, width, height);
    } finally {
      URL.revokeObjectURL(url);
    }
  } else if (webgl) {
    const rendered = await new Promise<HTMLCanvasElement>(resolve => {
      window.dispatchEvent(new CustomEvent("spike-capture-webgl-frame", { detail: { resolve } }));
    });
    drawContained(context, rendered, rendered.width, rendered.height, width, height);
  } else {
    throw new Error("The board viewport is not available for capture.");
  }
  return context.getImageData(0, 0, width, height);
}
