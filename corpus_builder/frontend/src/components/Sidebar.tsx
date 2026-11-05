import { useMemo, useState } from "react";
import { itemMatches, itemSubtitle, itemTitle } from "../items";
import type { DatasetResponse } from "../types";

interface SidebarProps {
  dataset: DatasetResponse;
  selected: number | null;
  onSelect: (index: number) => void;
}

export function Sidebar({ dataset, selected, onSelect }: SidebarProps) {
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return dataset.items
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => itemMatches(item, normalized));
  }, [dataset.items, query]);

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h1>Satyrn Dataset Viewer</h1>
        <p className="source-name" title={dataset.path}>
          {dataset.source}
        </p>
        <input
          className="search"
          type="search"
          placeholder="Filter items…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <span className="count">
          {visible.length} / {dataset.count} items
        </span>
        {dataset.errors.length > 0 && (
          <p className="warning">{dataset.errors.length} malformed line(s) were skipped.</p>
        )}
      </div>
      <nav className="item-list">
        {visible.map(({ item, index }) => (
          <button
            key={index}
            type="button"
            className={index === selected ? "item-link active" : "item-link"}
            onClick={() => onSelect(index)}
          >
            <span className="item-link-title">{itemTitle(item, index)}</span>
            <span className="item-link-meta">{itemSubtitle(item)}</span>
          </button>
        ))}
      </nav>
    </aside>
  );
}
