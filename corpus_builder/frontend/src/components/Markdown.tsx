import { useMemo } from "react";
import { renderMarkdown } from "../markdown";

interface MarkdownProps {
  source: string;
  className?: string;
}

/** Render markdown (with highlighted code fences) inside a `.markdown` div. */
export function Markdown({ source, className }: MarkdownProps) {
  const html = useMemo(() => renderMarkdown(source), [source]);
  return <div className={className ? `${className} markdown` : "markdown"} dangerouslySetInnerHTML={{ __html: html }} />;
}
