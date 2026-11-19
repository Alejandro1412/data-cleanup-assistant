import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type DragEvent } from "react";

import { api } from "../api";
import { keys, useHealth } from "../hooks";

interface Props {
  onOpen: (datasetId: string) => void;
}

const SAMPLE_URL = "/sample-customers.csv";

export function UploadPage({ onOpen }: Props) {
  const client = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const health = useHealth();
  const recent = useQuery({ queryKey: keys.datasets, queryFn: api.listDatasets });

  const upload = useMutation({
    mutationFn: api.upload,
    onSuccess: (dataset) => {
      void client.invalidateQueries({ queryKey: keys.datasets });
      onOpen(dataset.id);
    },
  });

  function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (file) upload.mutate(file);
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    handleFiles(event.dataTransfer.files);
  }

  async function useSample() {
    const response = await fetch(SAMPLE_URL);
    const blob = await response.blob();
    upload.mutate(new File([blob], "sample-customers.csv", { type: "text/csv" }));
  }

  return (
    <main className="upload">
      <div className="upload__intro">
        <h1>Clean up a CSV file</h1>
        <p>
          Upload a file to find duplicates, inconsistent spellings and formats, missing values and
          records that look wrong. Nothing changes until you accept a suggestion, and the original
          file is never modified.
        </p>
      </div>

      <div
        className={`dropzone ${dragging ? "dropzone--active" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <p className="dropzone__title">Drop a CSV file here</p>
        <p className="muted">Comma, semicolon, tab or pipe separated. Up to 20 MB.</p>
        <div className="dropzone__actions">
          <button
            className="button button--primary"
            onClick={() => input.current?.click()}
            disabled={upload.isPending}
          >
            {upload.isPending ? "Uploading…" : "Choose file"}
          </button>
          <button className="button" onClick={useSample} disabled={upload.isPending}>
            Try the sample file
          </button>
        </div>
        <input
          ref={input}
          type="file"
          accept=".csv,.tsv,.txt,text/csv"
          hidden
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {upload.isError && (
        <p className="notice notice--error" role="alert">
          {upload.error.message}
        </p>
      )}
      {health.data && !health.data.ai_enabled && (
        <p className="notice">
          AI review is off because the server has no API key. Rule-based checks still run; set
          ANTHROPIC_API_KEY on the server to also match synonyms, confirm duplicates and review
          records.
        </p>
      )}

      {recent.data && recent.data.length > 0 && (
        <section className="recent">
          <h2>Recent files</h2>
          <ul>
            {recent.data.map((d) => (
              <li key={d.id}>
                <button className="recent__item" onClick={() => onOpen(d.id)}>
                  <span>{d.filename}</span>
                  <span className="muted">
                    {d.status === "ready"
                      ? `${d.row_count.toLocaleString()} rows`
                      : d.status === "failed"
                        ? "Analysis failed"
                        : "Analyzing"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
