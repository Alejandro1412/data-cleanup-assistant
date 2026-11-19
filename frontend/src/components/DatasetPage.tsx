import { useState } from "react";

import { api } from "../api";
import { useDataset, useSuggestions } from "../hooks";
import { ColumnsPanel } from "./ColumnsPanel";
import { DataPanel } from "./DataPanel";
import { ReviewPanel } from "./ReviewPanel";

type Tab = "review" | "columns" | "data";

interface Props {
  datasetId: string;
  onBack: () => void;
}

export function DatasetPage({ datasetId, onBack }: Props) {
  const dataset = useDataset(datasetId);
  const ready = dataset.data?.status === "ready";
  const suggestions = useSuggestions(datasetId, ready);
  const [tab, setTab] = useState<Tab>("review");

  if (dataset.isError) {
    return (
      <main className="page">
        <p className="notice notice--error">{dataset.error.message}</p>
        <button className="button" onClick={onBack}>
          Upload another file
        </button>
      </main>
    );
  }
  if (!dataset.data) return <main className="page muted">Loading…</main>;

  const d = dataset.data;
  if (d.status === "failed") {
    return (
      <main className="page">
        <h1>{d.filename}</h1>
        <p className="notice notice--error">{d.error}</p>
        <button className="button" onClick={onBack}>
          Upload another file
        </button>
      </main>
    );
  }
  if (!ready) {
    return (
      <main className="page analyzing" aria-live="polite">
        <h1>{d.filename}</h1>
        <div className="analyzing__bar" aria-hidden="true" />
        <p>{d.progress ?? "Starting analysis"}…</p>
      </main>
    );
  }

  const items = suggestions.data ?? [];
  const decided = items.filter((s) => s.status !== "pending").length;
  const accepted = items.filter((s) => s.status === "accepted" && s.action !== "flag").length;

  return (
    <main className="page">
      <header className="dataset-header">
        <div>
          <button className="link" onClick={onBack}>
            Upload another file
          </button>
          <h1>{d.filename}</h1>
          <p className="muted">
            {d.row_count.toLocaleString()} rows, {d.columns.length} columns.{" "}
            {d.ai_model ? `Reviewed by rules and ${d.ai_model}.` : "Reviewed by rules only."}
          </p>
        </div>
        <div className="dataset-header__export">
          <div className="progress" aria-label="Review progress">
            <span className="progress__text">
              {decided.toLocaleString()} of {items.length.toLocaleString()} reviewed
            </span>
            <span className="progress__track">
              <span
                style={{ width: items.length ? `${(decided / items.length) * 100}%` : "0%" }}
              />
            </span>
          </div>
          <a className="button button--primary" href={api.exportUrl(datasetId)} download>
            Download cleaned file
          </a>
          <a className="button" href={api.auditUrl(datasetId)} download>
            Download change log
          </a>
          <p className="muted small">
            {accepted.toLocaleString()} accepted {accepted === 1 ? "change" : "changes"} will be
            applied.
          </p>
        </div>
      </header>

      {d.warnings.map((w) => (
        <p key={w} className="notice">
          {w}
        </p>
      ))}

      <div className="tabs" role="tablist">
        {(
          [
            ["review", "Review suggestions"],
            ["columns", "Columns"],
            ["data", "Data"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            role="tab"
            aria-selected={tab === value}
            className={`tab ${tab === value ? "tab--active" : ""}`}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {suggestions.isError && (
        <p className="notice notice--error">{suggestions.error.message}</p>
      )}
      {tab === "review" && suggestions.data && (
        <ReviewPanel datasetId={datasetId} suggestions={items} />
      )}
      {tab === "columns" && <ColumnsPanel profile={d.profile} />}
      {tab === "data" && <DataPanel datasetId={datasetId} suggestions={items} />}
    </main>
  );
}
