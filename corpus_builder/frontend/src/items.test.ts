import { describe, expect, it } from "vitest";
import { itemTitle } from "./items";

describe("itemTitle", () => {
  it("skips the system prompt", () => {
    const item = {
      prompt: [
        { role: "system", content: "You are a coding assistant." },
        { role: "user", content: "Fix render.py" },
      ],
    };

    expect(itemTitle(item, 0)).toBe("Fix render.py");
  });
});
