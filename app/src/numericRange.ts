/** Numerically safe extrema helpers for large solver and geometry datasets. */
export type NumericExtent = { minimum: number; maximum: number; count: number };

export function numericExtent(
  values: Iterable<number>,
  fallbackMinimum = 0,
  fallbackMaximum = fallbackMinimum,
): NumericExtent {
  let minimum = Number.POSITIVE_INFINITY;
  let maximum = Number.NEGATIVE_INFINITY;
  let count = 0;
  for (const value of values) {
    if (!Number.isFinite(value)) continue;
    if (value < minimum) minimum = value;
    if (value > maximum) maximum = value;
    count += 1;
  }
  return count ? { minimum, maximum, count } : { minimum: fallbackMinimum, maximum: fallbackMaximum, count: 0 };
}

export function numericMinimum(values: Iterable<number>, fallback = 0): number {
  return numericExtent(values, fallback, fallback).minimum;
}

export function numericMaximum(values: Iterable<number>, fallback = 0): number {
  return numericExtent(values, fallback, fallback).maximum;
}

export function absoluteMaximum(values: Iterable<number>, fallback = 0): number {
  let maximum = Number.NEGATIVE_INFINITY;
  for (const value of values) {
    if (!Number.isFinite(value)) continue;
    maximum = Math.max(maximum, Math.abs(value));
  }
  return maximum === Number.NEGATIVE_INFINITY ? fallback : maximum;
}
