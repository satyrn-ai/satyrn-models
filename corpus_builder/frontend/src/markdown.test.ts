import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./markdown";

describe("renderMarkdown", () => {
  it("renders prompt prose as markdown", () => {
    const html = renderMarkdown("Use the `Template` type from PEP 750.\n\n- first\n- second\n");

    expect(html).toContain("<p>");
    expect(html).toContain("<code>Template</code>");
    expect(html).toContain("<li>first</li>");
  });

  it("applies Python syntax highlighting to labelled fences", () => {
    const html = renderMarkdown("Reference solution:\n```python\ndef greeting(name: str) -> str:\n    return name\n```\n");

    expect(html).toContain('class="hljs language-python"');
    expect(html).toContain("hljs-keyword");
    expect(html).toContain("hljs-title");
  });

  it("applies Python syntax highlighting to unlabelled fences", () => {
    const html = renderMarkdown("Reference solution:\n```\ndef greeting(name: str) -> str:\n    return name\n```\n");

    expect(html).toContain('class="hljs language-python"');
    expect(html).toContain("hljs-keyword");
  });
});
