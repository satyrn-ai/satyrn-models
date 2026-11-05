import { useMemo } from "react";
import { escapeHtml, highlightPython } from "../markdown";

interface CodeBlockProps {
  code: string;
  language?: string;
}

export function CodeBlock({ code, language = "python" }: CodeBlockProps) {
  const html = useMemo(() => (language === "python" ? highlightPython(code) : escapeHtml(code)), [code, language]);
  return (
    <pre className="code">
      <code className={`hljs language-${language}`} dangerouslySetInnerHTML={{ __html: html }} />
    </pre>
  );
}
