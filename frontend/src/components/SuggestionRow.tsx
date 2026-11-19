import { useState, type FormEvent } from "react";

import { rowLabel } from "../labels";
import type { ReviewStatus, Suggestion } from "../types";
import { CellValue } from "./CellValue";

interface Props {
  suggestion: Suggestion;
  onReview: (status: ReviewStatus, finalValue?: string) => void;
}

const DECISION_TEXT: Record<Suggestion["action"], Record<"accepted" | "rejected", string>> = {
  set_value: { accepted: "Will change", rejected: "Skipped" },
  drop_row: { accepted: "Will remove", rejected: "Kept" },
  flag: { accepted: "Reviewed", rejected: "Dismissed" },
};

export function SuggestionRow({ suggestion: s, onReview }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(s.final_value ?? s.proposed_value ?? "");
  const pending = s.status === "pending";

  function submit(event: FormEvent) {
    event.preventDefault();
    onReview("accepted", draft);
    setEditing(false);
  }

  return (
    <li className={`suggestion suggestion--${s.status}`}>
      <div className="suggestion__where">
        <span className="suggestion__row">{rowLabel(s.row_index)}</span>
        {s.column && <span className="suggestion__column">{s.column}</span>}
      </div>

      <div className="suggestion__body">
        <div className="suggestion__change">
          {s.action === "set_value" && (
            <>
              <CellValue value={s.current_value} variant="removed" />
              <span className="suggestion__arrow" aria-label="becomes">
                ⟶
              </span>
              <CellValue
                value={s.final_value ?? s.proposed_value}
                variant={s.status === "rejected" ? "plain" : "added"}
              />
              {s.final_value !== null && <span className="tag">Edited</span>}
            </>
          )}
          {s.action === "flag" && (
            <>
              <CellValue value={s.current_value} />
              {s.final_value !== null && (
                <>
                  <span className="suggestion__arrow" aria-label="becomes">
                    ⟶
                  </span>
                  <CellValue value={s.final_value} variant="added" />
                </>
              )}
            </>
          )}
          {s.action === "drop_row" && (
            <span className="suggestion__drop">
              Remove this row
              {s.related_row_index !== null && `, keep ${rowLabel(s.related_row_index)}`}
            </span>
          )}
        </div>
        <p className="suggestion__reason">{s.reason}</p>
        <p className="suggestion__meta">
          <span className={`source source--${s.source}`}>
            {s.source === "ai" ? "AI" : "Rule"}
          </span>
          <span title="How sure the check is about this suggestion">
            {Math.round(s.confidence * 100)}% confident
          </span>
        </p>

        {editing && (
          <form className="suggestion__edit" onSubmit={submit}>
            <label className="visually-hidden" htmlFor={`edit-${s.id}`}>
              New value for {s.column}
            </label>
            <input
              id={`edit-${s.id}`}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              autoFocus
            />
            <button type="submit" className="button button--primary">
              Save value
            </button>
            <button type="button" className="button" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </form>
        )}
      </div>

      <div className="suggestion__actions">
        {pending && !editing && (
          <>
            {s.action === "set_value" && (
              <>
                <button className="button button--primary" onClick={() => onReview("accepted")}>
                  Apply
                </button>
                <button className="button" onClick={() => onReview("rejected")}>
                  Skip
                </button>
                <button className="button button--quiet" onClick={() => setEditing(true)}>
                  Edit
                </button>
              </>
            )}
            {s.action === "drop_row" && (
              <>
                <button className="button button--primary" onClick={() => onReview("accepted")}>
                  Remove row
                </button>
                <button className="button" onClick={() => onReview("rejected")}>
                  Keep row
                </button>
              </>
            )}
            {s.action === "flag" && (
              <>
                {s.column && (
                  <button className="button button--primary" onClick={() => setEditing(true)}>
                    Enter value
                  </button>
                )}
                <button className="button" onClick={() => onReview("accepted")}>
                  Leave as is
                </button>
              </>
            )}
          </>
        )}
        {!pending && (
          <>
            <span className={`decision decision--${s.status}`}>
              {DECISION_TEXT[s.action][s.status === "accepted" ? "accepted" : "rejected"]}
            </span>
            <button className="button button--quiet" onClick={() => onReview("pending")}>
              Undo
            </button>
          </>
        )}
      </div>
    </li>
  );
}
