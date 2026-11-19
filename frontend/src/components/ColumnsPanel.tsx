import type { ColumnProfile } from "../types";

const TYPE_LABELS: Record<string, string> = {
  identifier: "ID",
  integer: "Whole number",
  float: "Decimal number",
  boolean: "Yes / no",
  date: "Date",
  email: "Email",
  phone: "Phone",
  categorical: "Category",
  text: "Text",
  empty: "Empty",
};

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function ColumnsPanel({ profile }: { profile: ColumnProfile[] }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Column</th>
            <th scope="col">Detected type</th>
            <th scope="col" className="num">Filled</th>
            <th scope="col" className="num">Distinct values</th>
            <th scope="col">Examples</th>
          </tr>
        </thead>
        <tbody>
          {profile.map((column) => (
            <tr key={column.name}>
              <th scope="row">{column.name}</th>
              <td>
                {TYPE_LABELS[column.inferred_type] ?? column.inferred_type}
                {column.type_confidence < 1 && column.inferred_type !== "empty" && (
                  <span className="muted"> ({percent(column.type_confidence)} match)</span>
                )}
              </td>
              <td className="num">
                <span className="fill" aria-hidden="true">
                  <span style={{ width: percent(1 - column.null_ratio) }} />
                </span>
                {percent(1 - column.null_ratio)}
              </td>
              <td className="num">{column.distinct_count.toLocaleString()}</td>
              <td className="examples">{column.sample_values.slice(0, 4).join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
