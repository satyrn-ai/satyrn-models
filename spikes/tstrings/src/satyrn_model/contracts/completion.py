"""CompletionSpec: the closed candidate-assembly mode.

A ``CompletionSpec`` describes how a candidate is assembled for execution, not
how training data is rendered. The first and only mode in Task 1 is a complete
Python program: the candidate is executed as-is. Chat and FIM are *training
rendering* concerns (Task 7) and deliberately live elsewhere; a snapshot does
not carry them as candidate-assembly modes. The union is closed so an unknown
mode is a hard reject at ingest rather than a silent default.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Literal

from ._common import ContractError, require_object

COMPLETE_PROGRAM = "complete_program"


@dataclasses.dataclass(frozen=True, kw_only=True)
class CompleteProgram:
    """The candidate is a complete, self-contained Python program."""

    mode: Literal["complete_program"] = dataclasses.field(default=COMPLETE_PROGRAM)

    @classmethod
    def from_dict(cls, data: object) -> CompleteProgram:
        data = require_object(data, "completion")
        if set(data) - {"mode"}:
            extra = ", ".join(sorted(set(data) - {"mode"}))
            raise ContractError(f"completion has unexpected field(s): {extra}")
        if data.get("mode") != COMPLETE_PROGRAM:
            raise ContractError(f"unknown completion mode: {data.get('mode')!r}")
        return cls()

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode}


CompletionSpec = CompleteProgram


def completion_from_dict(data: object) -> CompletionSpec:
    d = require_object(data, "completion")
    if "mode" not in d:
        raise ContractError("completion must be an object with a 'mode'")
    mode = d["mode"]
    if mode == COMPLETE_PROGRAM:
        return CompleteProgram.from_dict(d)
    raise ContractError(f"unknown completion mode: {mode!r}")


__all__ = [
    "COMPLETE_PROGRAM",
    "CompleteProgram",
    "CompletionSpec",
    "completion_from_dict",
]
