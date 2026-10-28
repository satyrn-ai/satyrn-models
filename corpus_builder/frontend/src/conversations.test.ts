import { describe, expect, it } from "vitest";
import { collectMessages, messageContent, messageRoleLabel } from "./conversations";
import type { DatasetItem } from "./types";

describe("collectMessages", () => {
  it("combines SFT prompt and completion message lists", () => {
    const item: DatasetItem = {
      prompt: [{ role: "user", content: "How do I use `Template`?" }],
      completion: [{ role: "assistant", content: "Like this:\n\n```python\nTemplate(...)\n```" }],
    };

    const messages = collectMessages(item);

    expect(messages).toHaveLength(2);
    expect(messages.map(messageRoleLabel)).toEqual(["User", "Assistant"]);
    expect(messageContent(messages[0])).toBe("How do I use `Template`?");
  });

  it("attaches the trace to the first assistant message as reasoning", () => {
    const messages = collectMessages({
      prompt: [{ role: "user", content: "Q" }],
      completion: [{ role: "assistant", content: "A" }],
      trace: "Thinking it through.",
    });

    expect(messages[1].reasoning_content).toBe("Thinking it through.");
  });

  it("treats a plain string prompt as a single user message", () => {
    const messages = collectMessages({ prompt: "Explain PEP 750." });

    expect(messages).toEqual([{ role: "user", content: "Explain PEP 750." }]);
  });

  it("prefers an explicit messages list", () => {
    const messages = collectMessages({
      messages: [
        { role: "system", content: "You are concise." },
        { role: "user", content: "Hello" },
      ],
      prompt: "ignored",
    });

    expect(messages.map(messageRoleLabel)).toEqual(["System", "User"]);
  });

  it("returns no messages for rows without a conversation", () => {
    expect(collectMessages({ text: "A pretraining document." })).toEqual([]);
  });
});
