// SPDX-License-Identifier: MIT
import type { PdnReview, SolverResultBundle } from "./analysisResults";
import { pdnReviewView, type PdnCandidateDetail } from "./PiPdnReviewModel";

type Props = {
  source: SolverResultBundle | null;
  review: PdnReview | null;
  selectedNet: string;
  reviewSourceId: string | null;
};

const number = (value: number | undefined, digits = 5) =>
  typeof value === "number" && Number.isFinite(value) ? value.toPrecision(digits) : "Not returned";
const methodName = (method: PdnCandidateDetail["placement_method"]) => ({
  direct_port_shunt: "Direct port shunt",
  series_connection_path: "Lumped series connection path",
  multiport_impedance_loading: "Multiport impedance loading",
  invalid: "Invalid model",
})[method] ?? "Unknown model";

function Candidate({ candidate }: { candidate: PdnCandidateDetail }) {
  const accepted = candidate.status === "evaluated";
  const location = candidate.location;
  return <article className="pdn-candidate" aria-label={`PDN candidate ${candidate.id}`}>
    <h4>{candidate.id} — {accepted ? "Evaluated" : "Rejected"}</h4>
    <dl>
      <dt>Placement model</dt><dd>{methodName(candidate.placement_method)}</dd>
      <dt>Model status</dt><dd>{candidate.model_status || "Not returned"}</dd>
      <dt>Capacitor bank</dt><dd>{number(candidate.capacitance_f, 6)} F, {number(candidate.esr_ohm, 6)} ohm ESR, {number(candidate.esl_h, 6)} H ESL, count {candidate.count ?? "not returned"}</dd>
      <dt>Mounting path</dt><dd>{number(candidate.mounting_resistance_ohm, 6)} ohm, {number(candidate.mounting_inductance_h, 6)} H</dd>
      <dt>Candidate location</dt><dd>{location?.position_mm?.length === 2 ? `${number(location.position_mm[0])}, ${number(location.position_mm[1])} mm, ${location.layer ?? "layer not returned"}` : "No location model returned"}</dd>
      <dt>Worst impedance</dt><dd>{accepted ? `${number(candidate.worst_impedance_ohm)} ohm at ${number(candidate.worst_frequency_hz)} Hz` : "Unavailable"}</dd>
      <dt>Target comparison</dt><dd>{accepted ? `${candidate.passes_target ? "Within target" : "Target exceeded"}; ${candidate.violation_count} violating samples` : "Unavailable"}</dd>
      <dt>Worst impedance change</dt><dd>{accepted ? `${number(candidate.worst_impedance_improvement_percent)}% improvement; maximum local degradation ${number(candidate.maximum_local_degradation_percent)}%` : "Unavailable"}</dd>
    </dl>
    {candidate.assumptions?.length ? <div><b>Assumptions</b><ul>{candidate.assumptions.map((item, index) => <li key={index}>{item}</li>)}</ul></div> : <p>Assumptions were not returned.</p>}
    {candidate.issues?.length ? <ul aria-label="Candidate diagnostics">{candidate.issues.map((issue, index) => <li key={`${issue.code}-${index}`}>{issue.code}: {issue.message}</li>)}</ul> : null}
  </article>;
}

export default function PiPdnReview({ source, review, selectedNet, reviewSourceId }: Props) {
  const view = pdnReviewView(source, review, selectedNet, reviewSourceId);
  if (view.reason) return <section className="pdn-review-detail" aria-label="PDN candidate review"><h3>PDN candidate review</h3><p role="status">{view.reason}</p></section>;
  const admitted = view.review!;
  const portModel = source?.pdn_multiports?.find(item => item.net === admitted.net && item.source_result_id === source.analysis_id);
  return <section className="pdn-review-detail" aria-label="PDN candidate review">
    <h3>PDN target and candidate comparison</h3>
    <p>Source result {source!.analysis_id}; net {admitted.net}; model {admitted.model_status}. This is an engineering screen, not verified physical placement.</p>
    <p>Observation port: {portModel?.ports?.find(port => port.role === "observation")?.id ?? "Not returned"}. Return reference: {portModel?.reference?.kind ?? "Not returned"}. {portModel?.validity?.limits?.join(" ")}</p>
    <dl>
      <dt>Reviewed target</dt><dd>{number(admitted.target_ohm)} ohm</dd>
      <dt>Source worst impedance</dt><dd>{number(admitted.maximum_impedance_ohm)} ohm</dd>
      <dt>Source target status</dt><dd>{admitted.status === "pass" ? "Within target" : `Target exceeded at ${admitted.violation_count} samples`}</dd>
      <dt>Resonance peaks</dt><dd>{admitted.resonances?.length ?? "Not returned"}</dd>
      <dt>Antiresonance dips</dt><dd>{admitted.anti_resonances?.length ?? "Not returned"}</dd>
    </dl>
    {view.candidates.length ? view.candidates.map((candidate, index) => <Candidate key={`${candidate.id}-${index}`} candidate={candidate} />)
      : <p>No candidate banks were included in this review.</p>}
    <p>Direct port and lumped path models remain approximate. A multiport candidate inherits the source extraction limits. Candidate ranking requires independent board correlation before placement decisions.</p>
  </section>;
}
