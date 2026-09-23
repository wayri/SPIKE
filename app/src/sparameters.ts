export type ComplexValue = { re: number; im: number };

export type TouchstoneData = {
  name: string;
  portCount: number;
  frequenciesHz: number[];
  matrices: ComplexValue[][][];
  referenceOhm: number;
  sourceFormat: "RI" | "MA" | "DB";
  warnings: string[];
};

export type NetworkCheck = {
  passivity: "pass" | "fail";
  reciprocity: "pass" | "fail";
  worstSingularValue: number;
  worstReciprocityError: number;
};

const add = (a: ComplexValue, b: ComplexValue): ComplexValue => ({ re: a.re + b.re, im: a.im + b.im });
const multiply = (a: ComplexValue, b: ComplexValue): ComplexValue => ({
  re: a.re * b.re - a.im * b.im,
  im: a.re * b.im + a.im * b.re,
});
const conjugate = (value: ComplexValue): ComplexValue => ({ re: value.re, im: -value.im });
const magnitude = (value: ComplexValue) => Math.hypot(value.re, value.im);

const pairValue = (first: number, second: number, format: "RI" | "MA" | "DB"): ComplexValue => {
  if (format === "RI") return { re: first, im: second };
  const amplitude = format === "MA" ? first : 10 ** (first / 20);
  const phase = second * Math.PI / 180;
  return { re: amplitude * Math.cos(phase), im: amplitude * Math.sin(phase) };
};

export function parseTouchstone(name: string, source: string): TouchstoneData {
  const match = name.match(/\.s(\d+)p$/i);
  if (!match) throw new Error("Use a Touchstone filename with an .sNp suffix.");
  const portCount = Number(match[1]);
  if (!Number.isInteger(portCount) || portCount < 1 || portCount > 128) throw new Error("Touchstone port count is invalid.");

  let unit = "ghz";
  let parameter = "s";
  let format: "RI" | "MA" | "DB" = "MA";
  let referenceOhm = 50;
  const tokens: number[] = [];
  for (const [lineIndex, raw] of source.split(/\r?\n/).entries()) {
    const content = raw.split("!", 1)[0].trim();
    if (!content) continue;
    if (content.startsWith("#")) {
      const options = content.slice(1).trim().split(/\s+/);
      unit = options[0]?.toLowerCase() || unit;
      parameter = options[1]?.toLowerCase() || parameter;
      format = (options[2]?.toUpperCase() as typeof format) || format;
      const referenceIndex = options.findIndex(option => option.toLowerCase() === "r");
      if (referenceIndex >= 0) referenceOhm = Number(options[referenceIndex + 1]);
      continue;
    }
    if (content.startsWith("[")) {
      throw new Error("Touchstone 2 keyword files are supported by the SPIKE CLI; the desktop preview currently accepts Touchstone 1 full matrices.");
    }
    for (const token of content.split(/\s+/)) {
      const value = Number(token.replace(/[dD]/, "e"));
      if (!Number.isFinite(value)) throw new Error(`Invalid number '${token}' on line ${lineIndex + 1}.`);
      tokens.push(value);
    }
  }
  if (parameter !== "s") throw new Error("The desktop workbench currently accepts S-parameter Touchstone data. The CLI also converts Z and Y files.");
  if (!["RI", "MA", "DB"].includes(format)) throw new Error(`Unsupported Touchstone format ${format}.`);
  if (!(referenceOhm > 0)) throw new Error("Reference impedance must be positive.");
  const scale = ({ hz: 1, khz: 1e3, mhz: 1e6, ghz: 1e9 } as Record<string, number>)[unit];
  if (!scale) throw new Error(`Unsupported frequency unit ${unit}.`);

  const recordLength = 1 + 2 * portCount * portCount;
  if (!tokens.length || tokens.length % recordLength) throw new Error(`Incomplete ${portCount}-port Touchstone network record.`);
  const frequenciesHz: number[] = [];
  const matrices: ComplexValue[][][] = [];
  for (let offset = 0; offset < tokens.length; offset += recordLength) {
    frequenciesHz.push(tokens[offset] * scale);
    const matrix = Array.from({ length: portCount }, () =>
      Array.from({ length: portCount }, () => ({ re: 0, im: 0 })),
    );
    for (let pair = 0; pair < portCount * portCount; pair += 1) {
      const row = portCount === 2 ? pair % portCount : Math.floor(pair / portCount);
      const column = portCount === 2 ? Math.floor(pair / portCount) : pair % portCount;
      matrix[row][column] = pairValue(tokens[offset + 1 + pair * 2], tokens[offset + 2 + pair * 2], format);
    }
    matrices.push(matrix);
  }
  if (frequenciesHz.some((frequency, index) => index > 0 && frequency <= frequenciesHz[index - 1])) {
    throw new Error("Touchstone frequencies must be strictly increasing.");
  }
  const warnings = [];
  if (frequenciesHz[0] !== 0) warnings.push("No DC point; time-domain conversion requires an explicit extrapolation policy.");
  if (frequenciesHz.length > 2) {
    const spacing = frequenciesHz[1] - frequenciesHz[0];
    if (frequenciesHz.slice(2).some((frequency, index) => Math.abs((frequency - frequenciesHz[index + 1]) / spacing - 1) > 1e-5)) {
      warnings.push("Nonuniform frequency grid; time-domain conversion requires resampling.");
    }
  }
  return { name, portCount, frequenciesHz, matrices, referenceOhm, sourceFormat: format, warnings };
}

function largestSingularValue(matrix: ComplexValue[][]) {
  const count = matrix.length;
  let vector = Array.from({ length: count }, () => ({ re: 1 / Math.sqrt(count), im: 0 }));
  let eigenvalue = 0;
  for (let iteration = 0; iteration < 32; iteration += 1) {
    const forward = matrix.map(row => row.reduce((sum, value, index) => add(sum, multiply(value, vector[index])), { re: 0, im: 0 }));
    const next = Array.from({ length: count }, (_, column) =>
      matrix.reduce((sum, row, rowIndex) => add(sum, multiply(conjugate(row[column]), forward[rowIndex])), { re: 0, im: 0 }),
    );
    const norm = Math.sqrt(next.reduce((sum, value) => sum + magnitude(value) ** 2, 0));
    if (norm <= Number.EPSILON) return 0;
    vector = next.map(value => ({ re: value.re / norm, im: value.im / norm }));
    eigenvalue = norm;
  }
  return Math.sqrt(Math.max(0, eigenvalue));
}

export function checkNetwork(data: TouchstoneData): NetworkCheck {
  let worstSingularValue = 0;
  let worstReciprocityError = 0;
  for (const matrix of data.matrices) {
    worstSingularValue = Math.max(worstSingularValue, largestSingularValue(matrix));
    for (let row = 0; row < data.portCount; row += 1) {
      for (let column = row + 1; column < data.portCount; column += 1) {
        worstReciprocityError = Math.max(
          worstReciprocityError,
          magnitude({
            re: matrix[row][column].re - matrix[column][row].re,
            im: matrix[row][column].im - matrix[column][row].im,
          }),
        );
      }
    }
  }
  return {
    passivity: worstSingularValue <= 1 + 1e-9 ? "pass" : "fail",
    reciprocity: worstReciprocityError <= 1e-6 ? "pass" : "fail",
    worstSingularValue,
    worstReciprocityError,
  };
}

export function trace(data: TouchstoneData, destination: number, source: number) {
  let previousPhase: number | null = null;
  let accumulatedPhase = 0;
  return data.frequenciesHz.map((frequencyHz, index) => {
    const value = data.matrices[index][destination][source];
    const amplitude = magnitude(value);
    let phase = Math.atan2(value.im, value.re);
    if (previousPhase !== null) {
      while (phase - previousPhase > Math.PI) phase -= 2 * Math.PI;
      while (phase - previousPhase < -Math.PI) phase += 2 * Math.PI;
      accumulatedPhase += phase - previousPhase;
    } else {
      accumulatedPhase = phase;
    }
    previousPhase = phase;
    const denominator = { re: 1 - value.re, im: -value.im };
    const numerator = { re: 1 + value.re, im: value.im };
    const denominatorSquared = denominator.re ** 2 + denominator.im ** 2;
    const impedance = denominatorSquared > Number.EPSILON
      ? multiply(numerator, { re: denominator.re / denominatorSquared, im: -denominator.im / denominatorSquared })
      : { re: Number.POSITIVE_INFINITY, im: 0 };
    return {
      frequencyHz,
      magnitude: amplitude,
      magnitudeDb: 20 * Math.log10(Math.max(amplitude, 1e-300)),
      phaseDeg: accumulatedPhase * 180 / Math.PI,
      matchedInputImpedanceOhm: source === destination ? { re: impedance.re * data.referenceOhm, im: impedance.im * data.referenceOhm } : null,
    };
  });
}
