import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api } from "../api";
import { keys } from "../hooks";
import type { Suggestion } from "../types";

const PAGE_SIZE = 50;

interface Props {
  datasetId: string;
  suggestions: Suggestion[];
}

export function DataPanel({ datasetId, suggestions }: Props) {
  const [offset, setOffset] = useState(0);
  const { data, isPending, isError, error } = useQuery({
    queryKey: keys.rows(datasetId, offset),
    queryFn: () => api.getRows(datasetId, offset, PAGE_SIZE),
    placeholderData: keepPreviousData,
  });

  const byCell = useMemo(() => {
    const map = new Map<string, Suggestion>();
    for (const s of suggestions) {
      if (s.column && s.status !== "rejected") map.set(`${s.row_index}:${s.column}`, s);
    }
    return map;
  }, [suggestions]);
  const droppedRows = useMemo(
    () =>
      new Set(
        suggestions
          .filter((s) => s.action === "drop_row" && s.status !== "rejected")
          .map((s) => s.row_index),
      ),
    [suggestions],
  );

  if (isPending) return <p className="muted">Loading rows…</p>;
  if (isError) return <p className="notice notice--error">{error.message}</p>;

  const last = Math.min(offset + PAGE_SIZE, data.total);

  return (
    <>
      <p className="legend">
        <span className="legend__swatch legend__swatch--issue" /> Cell with a suggestion
        <span className="legend__swatch legend__swatch--drop" /> Row suggested for removal
      </p>
      <div className="table-wrap">
        <table className="table table--data">
          <thead>
            <tr>
              <th scope="col" className="num">Row</th>
              {data.columns.map((c) => (
                <th key={c} scope="col">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.index} className={droppedRows.has(row.index) ? "row--drop" : ""}>
                <th scope="row" className="num">
                  {row.index + 1}
                </th>
                {row.values.map((value, i) => {
                  const column = data.columns[i]!;
                  const suggestion = byCell.get(`${row.index}:${column}`);
                  return (
                    <td
                      key={column}
                      className={suggestion ? "cell--issue" : undefined}
                      title={suggestion?.reason}
                    >
                      {value}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pager">
        <button
          className="button"
          disabled={offset === 0}
          onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
        >
          Previous
        </button>
        <span>
          Rows {(offset + 1).toLocaleString()} to {last.toLocaleString()} of{" "}
          {data.total.toLocaleString()}
        </span>
        <button
          className="button"
          disabled={last >= data.total}
          onClick={() => setOffset((o) => o + PAGE_SIZE)}
        >
          Next
        </button>
      </div>
    </>
  );
}
