// SPDX-License-Identifier: Apache-2.0
/** Display-only bilinear interpolation of solved relative E-field amplitudes. */

export type EMergeAngularPattern = {
  frequency_hz: number;
  theta_deg: number[];
  phi_deg: number[];
  relative_amplitude_db: number[];
};

export function interpolateEMergePattern(pattern: EMergeAngularPattern, stepDeg = 5): EMergeAngularPattern {
  const { theta_deg: theta, phi_deg: phi, relative_amplitude_db: db } = pattern;
  if (!Number.isInteger(stepDeg) || stepDeg < 2 || stepDeg > 15 || 180 % stepDeg || 360 % stepDeg
      || theta.length < 2 || phi.length < 2 || db.length !== theta.length * phi.length
      || theta[0] !== 0 || theta[theta.length - 1] !== 180 || phi[0] !== 0 || phi[phi.length - 1] !== 360
      || theta.some((value, index) => !Number.isFinite(value) || (index > 0 && value <= theta[index - 1]))
      || phi.some((value, index) => !Number.isFinite(value) || (index > 0 && value <= phi[index - 1]))
      || db.some(value => !Number.isFinite(value) || value > 1 || value < -300)) {
    throw new Error("EMerge angular grid is not suitable for display interpolation.");
  }
  const find = (grid: number[], target: number) => {
    let high = 1;
    while (high < grid.length - 1 && grid[high] < target) high++;
    const low = high - 1;
    return [low, high, (target - grid[low]) / (grid[high] - grid[low])] as const;
  };
  const amplitude = (i: number, j: number) => 10 ** (db[i * phi.length + j] / 20);
  const output: number[] = [];
  const denseTheta = Array.from({ length: 180 / stepDeg + 1 }, (_, i) => i * stepDeg);
  const densePhi = Array.from({ length: 360 / stepDeg + 1 }, (_, i) => i * stepDeg);
  for (const t of denseTheta) {
    const [ti0, ti1, ft] = find(theta, t);
    for (const p of densePhi) {
      const [pi0, pi1, fp] = find(phi, p);
      const a0 = amplitude(ti0, pi0) * (1 - fp) + amplitude(ti0, pi1) * fp;
      const a1 = amplitude(ti1, pi0) * (1 - fp) + amplitude(ti1, pi1) * fp;
      output.push(20 * Math.log10(Math.max(a0 * (1 - ft) + a1 * ft, 1e-15)));
    }
  }
  return { frequency_hz: pattern.frequency_hz, theta_deg: denseTheta,
    phi_deg: densePhi, relative_amplitude_db: output };
}
