"""Capture all terminal output of a training job."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, TextIO


def strip_progress_output(line: str) -> str:
    """Return the line if it does not contain an escape sequence."""
    return "" if "\x1b" in line else line


def visible_text(line: str) -> str:
    """Return the text after the line's last carriage return: what a terminal would show."""
    return line.rsplit("\r", 1)[-1]


class Tee:
    """Write to a stream and a log file at once."""

    def __init__(self, stream: TextIO, log_file: IO[str]) -> None:
        self.stream = stream
        self.log_file = log_file
        self.pending_line = ""

    def write(self, new_text: str) -> int:
        buffered_text = self.pending_line + new_text
        buffered_lines = buffered_text.split("\n")
        self.pending_line = visible_text(buffered_lines.pop())

        for line in buffered_lines:
            self.append_to_log(line)
        return self.stream.write(new_text)

    def append_to_log(self, line: str) -> None:
        line = strip_progress_output(visible_text(line))
        if line.strip():
            self.log_file.write(line + "\n")

    def flush(self) -> None:
        self.stream.flush()
        self.log_file.flush()

    def isatty(self) -> bool:
        return self.stream.isatty()


@contextmanager
def tee_output(log_path: Path) -> Iterator[IO[str]]:
    """Duplicate stdout and stderr into log_path for the duration of the block."""
    original_stdout, original_stderr = sys.stdout, sys.stderr
    with log_path.open("a") as log_file:
        sys.stdout = Tee(original_stdout, log_file)
        sys.stderr = Tee(original_stderr, log_file)
        try:
            yield log_file
        finally:
            sys.stdout, sys.stderr = original_stdout, original_stderr
