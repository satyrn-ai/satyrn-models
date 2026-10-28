import { useEffect, useRef, useState } from "react";
import { ItemView } from "./components/ItemView";
import { Sidebar } from "./components/Sidebar";
import type { DatasetResponse } from "./types";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; dataset: DatasetResponse };

export function App() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch("/api/dataset");
        if (!response.ok) {
          throw new Error(`Request failed with status ${response.status}`);
        }
        const dataset = (await response.json()) as DatasetResponse;
        if (!cancelled) setState({ status: "ready", dataset });
      } catch (error) {
        if (!cancelled) setState({ status: "error", message: String(error) });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return <p className="loading">Loading dataset…</p>;
  }
  if (state.status === "error") {
    return <p className="error">Failed to load dataset: {state.message}</p>;
  }
  return <Viewer dataset={state.dataset} />;
}

function Viewer({ dataset }: { dataset: DatasetResponse }) {
  const [selected, setSelected] = useState<number | null>(dataset.items.length > 0 ? 0 : null);
  const contentRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (contentRef.current) contentRef.current.scrollTop = 0;
  }, [selected]);

  return (
    <div className="layout">
      <Sidebar dataset={dataset} selected={selected} onSelect={setSelected} />
      <main className="content" ref={contentRef}>
        {selected === null ? (
          <p className="empty">The dataset is empty.</p>
        ) : (
          <ItemView item={dataset.items[selected]} />
        )}
      </main>
    </div>
  );
}
