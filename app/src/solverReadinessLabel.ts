type Candidate = { eligible: boolean; state: string; missing: string[] };
/** Do not collapse runtime, adapter and numerical capability failures into 'gated'. */
export function solverReadinessLabel(candidate: Candidate): string {
  if (candidate.eligible) return 'eligible';
  if (candidate.state.includes('adapter') || candidate.state.includes('generator')) return 'adapter incomplete';
  if (['available', 'experimental', 'reference_validated', 'validated'].includes(candidate.state) && candidate.missing.length) return 'capability missing';
  if (candidate.state === 'not_catalogued') return 'not integrated';
  if (candidate.state === 'unavailable') return 'unavailable';
  return candidate.state.replace(/_/g, ' ') || 'unverified';
}
