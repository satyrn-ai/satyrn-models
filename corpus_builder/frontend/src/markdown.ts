/** Markdown and syntax-highlighting helpers. */

import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import { Marked } from "marked";
import { markedHighlight } from "marked-highlight";

// Only the Python grammar is registered: every generated dataset row contains
// Python code, so pulling in the full highlight.js bundle is unnecessary.
hljs.registerLanguage("python", python);

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Resolve a fence's language, defaulting unlabelled blocks to Python. */
function resolveLanguage(language: string | undefined): string {
  if (language && hljs.getLanguage(language)) {
    return language;
  }
  // Generated RL prompts are Python tasks, so a bare ``` block is Python code.
  return "python";
}

/** Highlight arbitrary code for a fenced block, defaulting to Python. */
export function highlightCode(code: string, language?: string): string {
  const resolved = resolveLanguage(language);
  return hljs.highlight(code, { language: resolved }).value;
}

/** Highlight a raw Python snippet, returning HTML for use inside a <code>. */
export function highlightPython(code: string): string {
  return highlightCode(code, "python");
}

const markdown = new Marked(
  markedHighlight({
    langPrefix: "hljs language-",
    highlight(code, language) {
      return highlightCode(code, language);
    },
  }),
  {
    // Give unlabelled fenced blocks an explicit language so that both the
    // highlighting and the `hljs language-python` class are applied.
    walkTokens(token) {
      if (token.type === "code" && !token.lang) {
        token.lang = "python";
      }
    },
  },
);

/** Render a markdown string, highlighting fenced code blocks. */
export function renderMarkdown(source: string): string {
  const result = markdown.parse(source, { async: false });
  return typeof result === "string" ? result : source;
}
