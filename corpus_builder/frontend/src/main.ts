import "highlight.js/styles/github-dark.css";
import "./style.css";
import { renderMarkdown, highlightPython, escapeHtml } from "./markdown";
import type { DatasetItem, DatasetResponse, TestCase } from "./types";

const app = document.querySelector<HTMLDivElement>("#app")!;

/** Keys handled explicitly by the renderer rather than the generic fallback. */
const KNOWN_KEYS = new Set(["prompt", "solution", "test_cases", "metadata", "_viewer"]);

function codeBlock(code: string, language = "python"): string {
  const highlighted = language === "python" ? highlightPython(code) : escapeHtml(code);
  return `<pre class="code"><code class="hljs language-${language}">${highlighted}</code></pre>`;
}

function humanizeKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function isCodeKey(key: string): boolean {
  return /(^|_)(code|solution|source|program)$/i.test(key) || key.endsWith("_code");
}

function itemTitle(item: DatasetItem, index: number): string {
  const metadata = item.metadata ?? {};
  const entryPoint = metadata.entry_point;
  if (typeof entryPoint === "string" && entryPoint) {
    return entryPoint;
  }
  const idea = metadata.idea;
  if (typeof idea === "string" && idea) {
    return idea;
  }
  const prompt = typeof item.prompt === "string" ? item.prompt.replace(/[#*`]/g, "").trim() : "";
  return prompt.split("\n")[0]?.slice(0, 60) || `Item ${index + 1}`;
}

function itemSubtitle(item: DatasetItem): string {
  const metadata = item.metadata ?? {};
  const parts = [metadata.pep, metadata.python_version && `Python ${metadata.python_version}`].filter(
    (part): part is string => typeof part === "string" && part.length > 0,
  );
  return parts.join(" · ");
}

function section(title: string, body: HTMLElement | string): HTMLElement {
  const wrapper = document.createElement("section");
  wrapper.className = "section";
  const heading = document.createElement("h3");
  heading.textContent = title;
  wrapper.append(heading);
  if (typeof body === "string") {
    const div = document.createElement("div");
    div.innerHTML = body;
    wrapper.append(div);
  } else {
    wrapper.append(body);
  }
  return wrapper;
}

function renderMetadata(metadata: Record<string, unknown>): HTMLElement {
  const grid = document.createElement("dl");
  grid.className = "metadata";
  for (const [key, value] of Object.entries(metadata)) {
    const dt = document.createElement("dt");
    dt.textContent = humanizeKey(key);
    const dd = document.createElement("dd");
    dd.textContent = typeof value === "string" ? value : JSON.stringify(value);
    grid.append(dt, dd);
  }
  return grid;
}

function renderTestCase(testCase: TestCase, index: number): HTMLElement {
  const card = document.createElement("article");
  card.className = "test-case";

  const heading = document.createElement("h4");
  const badge = document.createElement("span");
  badge.className = "badge";
  badge.textContent = String(index + 1);
  const name = document.createElement("span");
  name.textContent = testCase.name ?? `Test ${index + 1}`;
  heading.append(badge, name);
  card.append(heading);

  const fields: [string, string | undefined][] = [
    ["Input", testCase.input],
    ["Expected output", testCase.expected_output],
  ];
  const grid = document.createElement("div");
  grid.className = "test-grid";
  for (const [label, value] of fields) {
    if (value === undefined) continue;
    const cell = document.createElement("div");
    const caption = document.createElement("span");
    caption.className = "field-label";
    caption.textContent = label;
    const code = document.createElement("div");
    code.innerHTML = codeBlock(value);
    cell.append(caption, code);
    grid.append(cell);
  }
  if (grid.childElementCount > 0) {
    card.append(grid);
  }

  if (testCase.test_code) {
    const caption = document.createElement("span");
    caption.className = "field-label";
    caption.textContent = "Test code";
    const code = document.createElement("div");
    code.innerHTML = codeBlock(testCase.test_code);
    card.append(caption, code);
  }

  return card;
}

function renderGenericValue(key: string, value: unknown): HTMLElement {
  const container = document.createElement("div");
  if (typeof value === "string") {
    if (isCodeKey(key)) {
      container.innerHTML = codeBlock(value);
    } else {
      container.innerHTML = `<div class="markdown">${renderMarkdown(value)}</div>`;
    }
    return container;
  }
  container.innerHTML = codeBlock(JSON.stringify(value, null, 2), "json");
  return container;
}

function renderItem(item: DatasetItem): HTMLElement {
  const article = document.createElement("article");
  article.className = "item";

  const index = item._viewer?.index ?? 0;
  const header = document.createElement("header");
  header.className = "item-header";
  const title = document.createElement("h2");
  title.textContent = itemTitle(item, index);
  const subtitle = document.createElement("p");
  subtitle.className = "item-subtitle";
  subtitle.textContent = itemSubtitle(item);
  header.append(title, subtitle);
  article.append(header);

  if (item.metadata && Object.keys(item.metadata).length > 0) {
    article.append(section("Metadata", renderMetadata(item.metadata)));
  }

  if (typeof item.prompt === "string" && item.prompt) {
    article.append(section("Prompt", `<div class="markdown">${renderMarkdown(item.prompt)}</div>`));
  }

  if (typeof item.solution === "string" && item.solution) {
    article.append(section("Reference solution", codeBlock(item.solution)));
  }

  if (Array.isArray(item.test_cases) && item.test_cases.length > 0) {
    const wrapper = document.createElement("div");
    wrapper.className = "test-cases";
    item.test_cases.forEach((testCase, testIndex) => wrapper.append(renderTestCase(testCase, testIndex)));
    article.append(section(`Test cases (${item.test_cases.length})`, wrapper));
  }

  for (const [key, value] of Object.entries(item)) {
    if (KNOWN_KEYS.has(key) || value === null || value === undefined) continue;
    if (typeof value === "string" && value === "") continue;
    article.append(section(humanizeKey(key), renderGenericValue(key, value)));
  }

  return article;
}

function start(response: DatasetResponse): void {
  const layout = document.createElement("div");
  layout.className = "layout";

  const sidebar = document.createElement("aside");
  sidebar.className = "sidebar";
  const sidebarHeader = document.createElement("div");
  sidebarHeader.className = "sidebar-header";
  sidebarHeader.innerHTML = `<h1>Satyrn Dataset Viewer</h1>`;

  const sourceName = document.createElement("p");
  sourceName.className = "source-name";
  sourceName.textContent = response.source;
  sourceName.title = response.path;

  const search = document.createElement("input");
  search.className = "search";
  search.type = "search";
  search.placeholder = "Filter items…";

  const count = document.createElement("span");
  count.className = "count";

  const list = document.createElement("nav");
  list.className = "item-list";

  sidebarHeader.append(sourceName, search, count);
  sidebar.append(sidebarHeader, list);

  const content = document.createElement("main");
  content.className = "content";

  layout.append(sidebar, content);
  app.replaceChildren(layout);

  if (response.errors.length > 0) {
    const warning = document.createElement("p");
    warning.className = "warning";
    warning.textContent = `${response.errors.length} malformed line(s) were skipped.`;
    sidebarHeader.append(warning);
  }

  function select(index: number): void {
    list.querySelectorAll("button").forEach((button, buttonIndex) => {
      button.classList.toggle("active", buttonIndex === index);
    });
    content.replaceChildren(renderItem(response.items[index]));
    content.scrollTop = 0;
  }

  function matches(item: DatasetItem, query: string): boolean {
    if (!query) return true;
    const haystack = JSON.stringify(item).toLowerCase();
    return haystack.includes(query);
  }

  function populate(query: string): void {
    list.replaceChildren();
    const normalized = query.trim().toLowerCase();
    let visible = 0;
    response.items.forEach((item, index) => {
      if (!matches(item, normalized)) return;
      visible += 1;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "item-link";
      const label = document.createElement("span");
      label.className = "item-link-title";
      label.textContent = itemTitle(item, index);
      const meta = document.createElement("span");
      meta.className = "item-link-meta";
      meta.textContent = itemSubtitle(item);
      button.append(label, meta);
      button.addEventListener("click", () => select(index));
      list.append(button);
    });
    count.textContent = `${visible} / ${response.count} items`;
  }

  search.addEventListener("input", () => populate(search.value));
  populate("");

  if (response.items.length > 0) {
    select(0);
  } else {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "The dataset is empty.";
    content.append(empty);
  }
}

async function bootstrap(): Promise<void> {
  app.innerHTML = `<p class="loading">Loading dataset…</p>`;
  try {
    const response = await fetch("/api/dataset");
    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }
    start((await response.json()) as DatasetResponse);
  } catch (error) {
    app.innerHTML = `<p class="error">Failed to load dataset: ${escapeHtml(String(error))}</p>`;
  }
}

void bootstrap();
