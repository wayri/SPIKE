// SPDX-License-Identifier: Apache-2.0
import DataTable from "./DataTable";

export default function SourceCapacityResults({ status, rows }: { status: unknown; rows: Record<string, unknown>[] }) {
  if (!rows.length || status === "not_requested") return null;
  const amps = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? `${value.toPrecision(5)} A` : "Not determined";
  return <section className="wizard-section" aria-label="Source current capacity">
    <h4>Source capacity · {String(status ?? "not determined")}</h4>
    <p>Required current is the solved demand at the requested voltage. An exceeded limit means the configured sinks cannot all be sustained; a reduced-voltage operating point was not solved.</p>
    <DataTable label="Source current limits and multi-sink demand" pageSize={20}>
      <thead><tr><th>Source</th><th>Demand</th><th>Limit</th><th>Headroom</th><th>Status</th></tr></thead>
      <tbody>{rows.map((row, index) => <tr key={`${row.id}-${index}`}><td>{String(row.id ?? "Unassigned")}</td>
        <td>{amps(row.forward_current_a)}</td><td>{row.current_limit_a === null ? "Unlimited" : amps(row.current_limit_a)}</td>
        <td>{row.current_limit_a === null ? "Unlimited" : amps(row.headroom_a)}</td><td>{String(row.status ?? "not determined")}</td></tr>)}</tbody>
    </DataTable>
  </section>;
}
