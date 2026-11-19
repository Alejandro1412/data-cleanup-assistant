import { useEffect, useState } from "react";

import { DatasetPage } from "./components/DatasetPage";
import { UploadPage } from "./components/UploadPage";

const DATASET_HASH = /^#\/datasets\/([a-f0-9]+)$/;

function datasetFromHash(): string | null {
  return DATASET_HASH.exec(window.location.hash)?.[1] ?? null;
}

/** Two screens do not need a router; the URL hash keeps links and reloads working. */
export function App() {
  const [datasetId, setDatasetId] = useState(datasetFromHash);

  useEffect(() => {
    const onChange = () => setDatasetId(datasetFromHash());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const open = (id: string) => {
    window.location.hash = `/datasets/${id}`;
  };
  const back = () => {
    window.location.hash = "";
  };

  return (
    <>
      <header className="topbar">
        <a href="#" className="topbar__name">
          Data Cleanup Assistant
        </a>
      </header>
      {datasetId ? (
        <DatasetPage key={datasetId} datasetId={datasetId} onBack={back} />
      ) : (
        <UploadPage onOpen={open} />
      )}
    </>
  );
}
