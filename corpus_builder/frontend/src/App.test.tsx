// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { DatasetResponse } from "./types";

const dataset: DatasetResponse = {
  source: "test.jsonl",
  path: "/data/test.jsonl",
  count: 2,
  errors: [],
  items: [
    {
      prompt: [{ role: "user", content: "How do I use `Template`?" }],
      completion: [{ role: "assistant", content: "```\ndef f():\n    pass\n```" }],
      trace: "Thinking it through.",
      metadata: { entry_point: "first_item", pep: "PEP 750" },
      _viewer: { index: 0, line: 1 },
    },
    {
      prompt: "Write a parser.",
      solution: "def parse():\n    pass",
      test_cases: [{ name: "parses", input: "x", expected_output: "y" }],
      metadata: { entry_point: "second_item" },
      _viewer: { index: 1, line: 2 },
    },
  ],
};

function mockFetch(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(dataset), { status: 200 })),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders the first item's conversation with thinking and highlighted code", async () => {
    mockFetch();
    const { container } = render(<App />);

    expect(await screen.findByRole("heading", { level: 2, name: "first_item" })).toBeTruthy();
    expect(screen.getByText("2 / 2 items")).toBeTruthy();
    expect(screen.getByText("Thinking")).toBeTruthy();
    expect(container.querySelector(".message-user code")?.textContent).toBe("Template");
    expect(container.querySelector(".message-assistant .hljs-keyword")).not.toBeNull();
  });

  it("selects items from the sidebar and filters the list", async () => {
    mockFetch();
    const { container } = render(<App />);
    await screen.findByRole("heading", { level: 2, name: "first_item" });

    fireEvent.click(screen.getByRole("button", { name: /second_item/ }));
    expect(screen.getByRole("heading", { level: 2, name: "second_item" })).toBeTruthy();
    expect(screen.getByText("Test cases (1)")).toBeTruthy();
    expect(container.querySelector(".item-link.active")?.textContent).toContain("second_item");

    fireEvent.change(screen.getByPlaceholderText("Filter items…"), { target: { value: "parser" } });
    expect(screen.getByText("1 / 2 items")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /first_item/ })).toBeNull();
  });

  it("reports a failed request", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("", { status: 500 })),
    );
    render(<App />);

    expect(await screen.findByText(/Failed to load dataset: .*500/)).toBeTruthy();
  });
});
