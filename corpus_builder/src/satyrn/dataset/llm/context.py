"""Prompt context: system prompt, reference documents, and expected output shape."""

import json
from collections import OrderedDict
from pathlib import Path


class Context:
    """Bundle a system prompt, reference documents, and an expected output shape for a model call."""

    def __init__(self) -> None:
        self.system_prompt = ""
        self.documents: OrderedDict[str, str] = OrderedDict()
        self.expect_json = False
        self.json_schema: dict | None = None
        self.json_prompt: str | None = None

    def add(self, title: str, document: str | Path) -> None:
        """Attach a titled document to the context."""
        text = document.read_text() if isinstance(document, Path) else document
        self.documents[title] = text

    def set_json_schema(self, schema: dict) -> None:
        """Require the model's response to conform to a JSON schema."""
        self.json_schema = schema
        self.expect_json = True

    def set_json_prompt(self, text: str) -> None:
        """Describe the expected JSON output shape in prose instead of a schema."""
        self.json_prompt = text
        self.expect_json = True

    def render(self, prompt: str) -> str:
        """Return prompt with complete context."""
        parts = []
        if self.json_schema:
            parts.append(f"Respond only with JSON matching this schema:\n{json.dumps(self.json_schema)}")
        if self.json_prompt:
            parts.append(self.json_prompt)
        for title, document in self.documents.items():
            parts.append(f"--- {title} ---\n{document}")
        parts.append(prompt)
        return "\n\n".join(parts)
