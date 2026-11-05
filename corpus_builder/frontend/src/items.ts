/** Helpers for labelling dataset rows and their fields. */

import { collectMessages } from "./conversations";
import type { DatasetItem } from "./types";

/** Keys handled explicitly by the renderer rather than the generic fallback. */
export const KNOWN_KEYS = new Set(["prompt", "completion", "messages", "solution", "test_cases", "metadata", "trace", "_viewer"]);

export function humanizeKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function isCodeKey(key: string): boolean {
  return /(^|_)(code|solution|source|program)$/i.test(key) || key.endsWith("_code");
}

export function itemTitle(item: DatasetItem, index: number): string {
  const metadata = item.metadata ?? {};
  const entryPoint = metadata.entry_point;
  if (typeof entryPoint === "string" && entryPoint) {
    return entryPoint;
  }
  const idea = metadata.idea;
  if (typeof idea === "string" && idea) {
    return idea;
  }
  const prompt = collectMessages(item)
    .map((message) => (typeof message.content === "string" ? message.content : ""))
    .find((content) => content.length > 0);
  const cleaned = prompt?.replace(/[#*`]/g, "").trim() ?? "";
  return cleaned.split("\n")[0]?.slice(0, 60) || `Item ${index + 1}`;
}

export function itemSubtitle(item: DatasetItem): string {
  const metadata = item.metadata ?? {};
  const parts = [metadata.pep, metadata.python_version && `Python ${metadata.python_version}`].filter(
    (part): part is string => typeof part === "string" && part.length > 0,
  );
  return parts.join(" · ");
}

/** Return true when a lower-cased query appears anywhere in the item. */
export function itemMatches(item: DatasetItem, query: string): boolean {
  if (!query) return true;
  return JSON.stringify(item).toLowerCase().includes(query);
}
