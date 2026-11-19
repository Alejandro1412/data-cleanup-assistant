import { useMemo, useState } from "react";

import { useReview } from "../hooks";
import { groupTitle, KIND_LABELS, KIND_ORDER } from "../labels";
import type { IssueKind, ReviewStatus, Source, Suggestion } from "../types";
import { SuggestionRow } from "./SuggestionRow";

interface Props {
  datasetId: string;
  suggestions: Suggestion[];
}

type StatusFilter = ReviewStatus | "all";
type SourceFilter = Source | "all";

const PREVIEW_SIZE = 5;
const CONFIDENCE_OPTIONS = [
  { value: 0, label: "Any confidence" },
  { value: 0.5, label: "50% or more" },
  { value: 0.8, label: "80% or more" },
  { value: 0.9, label: "90% or more" },
];

interface Group {
  key: string;
  title: string;
  items: Suggestion[];
}

function groupSuggestions(items: Suggestion[]): Group[] {
  const groups = new Map<string, Suggestion[]>();
  for (const item of items) {
    const list = groups.get(item.group_key);
    if (list) list.push(item);
    else groups.set(item.group_key, [item]);
  }
  return [...groups.entries()]
    .map(([key, list]) => ({ key, title: groupTitle(key, list[0]!), items: list }))
    .sort((a, b) => b.items.length - a.items.length);
}

/** Pending items a bulk action can safely decide: flags need a human look. */
function bulkTargets(items: Suggestion[]): Suggestion[] {
  return items.filter((s) => s.status === "pending" && s.action !== "flag");
}

export function ReviewPanel({ datasetId, suggestions }: Props) {
  const review = useReview(datasetId);
  const [kind, setKind] = useState<IssueKind | "all">("all");
  const [status, setStatus] = useState<StatusFilter>("pending");
  const [source, setSource] = useState<SourceFilter>("all");
  const [minConfidence, setMinConfidence] = useState(0);

  const pendingByKind = useMemo(() => {
    const counts = new Map<IssueKind, number>();
    for (const s of suggestions) {
      if (s.status === "pending") counts.set(s.kind, (counts.get(s.kind) ?? 0) + 1);
    }
    return counts;
  }, [suggestions]);

  const visible = useMemo(
    () =>
      suggestions.filter(
        (s) =>
          (kind === "all" || s.kind === kind) &&
          (status === "all" || s.status === status) &&
          (source === "all" || s.source === source) &&
          s.confidence >= minConfidence,
      ),
    [suggestions, kind, status, source, minConfidence],
  );
  const groups = useMemo(() => groupSuggestions(visible), [visible]);
  const visibleTargets = bulkTargets(visible);
  const kindsPresent = KIND_ORDER.filter((k) => suggestions.some((s) => s.kind === k));
  const totalPending = suggestions.filter((s) => s.status === "pending").length;

  function decide(ids: string[], next: ReviewStatus, finalValue?: string) {
    if (ids.length) review.mutate({ ids, status: next, finalValue });
  }

  return (
    <div className="review">
      <nav className="review__nav" aria-label="Issue types">
        <button
          className={`nav-item ${kind === "all" ? "nav-item--active" : ""}`}
          onClick={() => setKind("all")}
          aria-pressed={kind === "all"}
        >
          <span>All issues</span>
          <span className="nav-item__count">{totalPending}</span>
        </button>
        {kindsPresent.map((k) => (
          <button
            key={k}
            className={`nav-item ${kind === k ? "nav-item--active" : ""}`}
            onClick={() => setKind(k)}
            aria-pressed={kind === k}
          >
            <span>{KIND_LABELS[k]}</span>
            <span className="nav-item__count">{pendingByKind.get(k) ?? 0}</span>
          </button>
        ))}
        <p className="review__nav-note">Counts show suggestions still waiting for a decision.</p>
      </nav>

      <section className="review__main" aria-label="Suggestions">
        <div className="filters">
          <label>
            <span className="visually-hidden">Status</span>
            <select value={status} onChange={(e) => setStatus(e.target.value as StatusFilter)}>
              <option value="pending">Waiting for review</option>
              <option value="accepted">Accepted</option>
              <option value="rejected">Rejected</option>
              <option value="all">All decisions</option>
            </select>
          </label>
          <label>
            <span className="visually-hidden">Source</span>
            <select value={source} onChange={(e) => setSource(e.target.value as SourceFilter)}>
              <option value="all">Rules and AI</option>
              <option value="rule">Rules only</option>
              <option value="ai">AI only</option>
            </select>
          </label>
          <label>
            <span className="visually-hidden">Minimum confidence</span>
            <select
              value={minConfidence}
              onChange={(e) => setMinConfidence(Number(e.target.value))}
            >
              {CONFIDENCE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <span className="filters__spacer" />
          <button
            className="button button--primary"
            disabled={!visibleTargets.length}
            onClick={() => decide(visibleTargets.map((s) => s.id), "accepted")}
          >
            Accept {visibleTargets.length.toLocaleString()} shown
          </button>
        </div>

        {review.isError && (
          <p className="notice notice--error" role="alert">
            {review.error.message} Your last change was not saved.
          </p>
        )}

        {groups.length === 0 ? (
          <div className="empty">
            {totalPending === 0 && suggestions.length > 0 ? (
              <>
                <h3>Everything has been reviewed</h3>
                <p>Download the cleaned file from the top of the page.</p>
              </>
            ) : suggestions.length === 0 ? (
              <>
                <h3>No problems found</h3>
                <p>The checks did not find anything to fix in this file.</p>
              </>
            ) : (
              <>
                <h3>Nothing matches these filters</h3>
                <p>Change the filters above to see more suggestions.</p>
              </>
            )}
          </div>
        ) : (
          groups.map((group) => (
            <GroupCard key={group.key} group={group} onDecide={decide} />
          ))
        )}
      </section>
    </div>
  );
}

function GroupCard({
  group,
  onDecide,
}: {
  group: Group;
  onDecide: (ids: string[], status: ReviewStatus, finalValue?: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const targets = bulkTargets(group.items);
  const shown = expanded ? group.items : group.items.slice(0, PREVIEW_SIZE);
  const sample = group.items[0]!;
  const commonTarget =
    sample.action === "set_value" &&
    group.items.every((s) => s.proposed_value === sample.proposed_value)
      ? sample.proposed_value
      : null;

  return (
    <article className="group">
      <header className="group__header">
        <div>
          <h3 className="group__title">{group.title}</h3>
          <p className="group__summary">
            {group.items.length.toLocaleString()}{" "}
            {group.items.length === 1 ? "suggestion" : "suggestions"}
            {commonTarget !== null && commonTarget !== "" && <> to change to “{commonTarget}”</>}
          </p>
        </div>
        {targets.length > 1 && (
          <div className="group__actions">
            <button
              className="button button--primary"
              onClick={() => onDecide(targets.map((s) => s.id), "accepted")}
            >
              Accept all {targets.length}
            </button>
            <button
              className="button"
              onClick={() => onDecide(targets.map((s) => s.id), "rejected")}
            >
              Reject all
            </button>
          </div>
        )}
      </header>
      <ul className="group__list">
        {shown.map((s) => (
          <SuggestionRow
            key={s.id}
            suggestion={s}
            onReview={(next, value) => onDecide([s.id], next, value)}
          />
        ))}
      </ul>
      {group.items.length > PREVIEW_SIZE && (
        <button className="group__more" onClick={() => setExpanded((v) => !v)}>
          {expanded ? "Show fewer" : `Show all ${group.items.length.toLocaleString()}`}
        </button>
      )}
    </article>
  );
}
