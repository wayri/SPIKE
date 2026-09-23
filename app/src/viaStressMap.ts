import type { ScalarSample } from "./analysisResults";

const escape = (value: string) => value.replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]!));

/** Top-view source XY map. Spatial bins retain the peak, never an average. */
export function viaStressMapSvg(samples: readonly ScalarSample[]): string {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity, peak = 0, count = 0;
  for (const s of samples) {
    if (![s.x_mm, s.y_mm, s.value].every(Number.isFinite)) continue;
    minX = Math.min(minX, s.x_mm); maxX = Math.max(maxX, s.x_mm);
    minY = Math.min(minY, s.y_mm); maxY = Math.max(maxY, s.y_mm);
    peak = Math.max(peak, Math.abs(s.value)); count++;
  }
  if (!count) return '<p>No finite, positioned via-current-density samples. No stress map inferred.</p>';
  const scale = 440 / Math.max(maxX - minX, maxY - minY, 0.001);
  const bins = new Map<string, { x: number; y: number; sample: ScalarSample }>();
  for (const sample of samples) {
    if (![sample.x_mm, sample.y_mm, sample.value].every(Number.isFinite)) continue;
    const x = 30 + (sample.x_mm - minX) * scale, y = 30 + (sample.y_mm - minY) * scale;
    const key = `${Math.floor(x / 4)},${Math.floor(y / 4)}`;
    const prior = bins.get(key);
    if (!prior || Math.abs(sample.value) > Math.abs(prior.sample.value)) bins.set(key, { x, y, sample });
  }
  const marks = [...bins.values()].map(({ x, y, sample }) => {
    const fraction = peak ? Math.abs(sample.value) / peak : 0;
    const title = escape(`${sample.element_id ?? 'Via sample'} | ${sample.net ?? '-'} | ${sample.layer ?? '-'} | ${Math.abs(sample.value)} A/mm2 | X ${sample.x_mm}, Y ${sample.y_mm} mm`);
    return `<circle cx="${x}" cy="${y}" r="3" fill="hsl(${220 * (1 - fraction)},85%,55%)"><title>${title}</title></circle>`;
  }).join('');
  return `<figure><svg viewBox="0 0 500 500" role="img" aria-label="Via electrical stress map, source XY top view" style="width:100%;max-width:560px;background:#101820"><text x="15" y="18" fill="#d9e5eb">Source XY: +X right, +Y down (mm)</text>${marks}</svg><figcaption>${count} samples; ${bins.size} peak-preserving spatial markers. Blue 0 to red ${peak.toPrecision(6)} A/mm2. Layer spans overlap in this top view. Electrical current density only—not mechanical stress, fatigue or thermal qualification.</figcaption></figure>`;
}
