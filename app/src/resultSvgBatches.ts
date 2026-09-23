import type { ScalarSample } from "./analysisResults";

export type SvgScalarBatch = { bucket: number; color: string; path: string; sampleCount: number };

type Options = {
  minimum: number;
  maximum: number;
  cellSize: number;
  smooth: boolean;
  project: (point: [number, number]) => [number, number];
  colorBuckets?: number;
};

const finite = (value: number) => Number.isFinite(value) ? value : 0;
const coordinate = (value: number) => finite(value).toFixed(5).replace(/\.?0+$/, "");

function projectedArea(points: [number, number][]): number {
  if (points.length < 3) return 0;
  return Math.abs(points.reduce((sum, point, index) => {
    const next = points[(index + 1) % points.length];
    return sum + point[0] * next[1] - next[0] * point[1];
  }, 0)) / 2;
}

function fallbackCell(sample: ScalarSample, options: Options): string {
  const [x, y] = options.project([sample.x_mm, sample.y_mm]);
  const radius = options.cellSize * (options.smooth ? 1.28 : 0.5);
  if (options.smooth) {
    return `M${coordinate(x - radius)},${coordinate(y)}a${coordinate(radius)},${coordinate(radius)} 0 1,0 ${coordinate(radius * 2)},0a${coordinate(radius)},${coordinate(radius)} 0 1,0 ${coordinate(-radius * 2)},0Z`;
  }
  return `M${coordinate(x - radius)},${coordinate(y - radius)}h${coordinate(radius * 2)}v${coordinate(radius * 2)}h${coordinate(-radius * 2)}Z`;
}

/**
 * Convert a scalar field into a bounded number of SVG paths. Solver samples
 * remain distinct path sub-shapes, but no longer create one React/DOM node per
 * cell. Color quantization is display-only and never changes result values.
 */
export function buildScalarSvgBatches(samples: ScalarSample[], options: Options): SvgScalarBatch[] {
  const bucketCount = Math.max(8, Math.min(128, Math.floor(options.colorBuckets ?? 48)));
  const span = options.maximum - options.minimum;
  const paths = new Map<number, string[]>();
  const counts = new Map<number, number>();
  samples.forEach(sample => {
    const ratio = span > 0 ? Math.max(0, Math.min(1, (sample.value - options.minimum) / span)) : 0.5;
    const bucket = Math.round(ratio * (bucketCount - 1));
    const commands = paths.get(bucket) ?? [];
    if ((sample.vertices_mm?.length ?? 0) >= 3) {
      const points = sample.vertices_mm!.map(vertex => options.project([vertex[0], vertex[1]]));
      // Vertical faces collapse to a zero-area path in the 2D projection. Use
      // the authoritative sample centre as a bounded visible glyph instead.
      commands.push(projectedArea(points) > 1e-10
        ? `${points.map((point, index) => `${index ? "L" : "M"}${coordinate(point[0])},${coordinate(point[1])}`).join("")}Z`
        : fallbackCell(sample, options));
    } else {
      commands.push(fallbackCell(sample, options));
    }
    paths.set(bucket, commands);
    counts.set(bucket, (counts.get(bucket) ?? 0) + 1);
  });
  return [...paths.entries()].sort(([left], [right]) => left - right).map(([bucket, commands]) => {
    const ratio = bucket / Math.max(bucketCount - 1, 1);
    return {
      bucket,
      color: `hsl(${(1 - ratio) * 220} 92% 56%)`,
      path: commands.join(" "),
      sampleCount: counts.get(bucket) ?? 0,
    };
  });
}
