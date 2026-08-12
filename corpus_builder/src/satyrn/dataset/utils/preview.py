from rich.console import Console
from rich.markdown import Markdown

console = Console()


def print_messages(messages: list[dict[str, str]]) -> None:
    """Print messages in a conversation."""
    role_colors = {"user": "cyan", "assistant": "green", "system": "yellow"}

    for msg in messages:
        color = role_colors.get(msg["role"], "white")
        console.rule(f"[bold {color}]{msg['role']}[/bold {color}]")
        console.print(Markdown(msg["content"]))
        console.print()


def print_dataset_line(dataset_line: dict) -> None:
    """Print a dataset line with messages and metadata."""
    console.rule("[bold blue]Dataset Line[/bold blue]")
    fields = ["filename", "python_version", "idea"]
    for key in fields:
        if dataset_line.get(key):
            console.print(f"[bold]{key}:[/bold] {dataset_line[key]}")

    markdown_fields = ["code", "trace", "expected_output"]
    for key in markdown_fields:
        if dataset_line.get(key):
            console.print(f"[bold]{key}:[/bold]")
            text = f"```python\n{dataset_line[key]}\n```" if key == "code" else dataset_line[key]
            console.print(Markdown(text))

    known_keys = set(fields) | set(markdown_fields) | {"messages"}
    for key, value in dataset_line.items():
        if key not in known_keys and value:
            console.print(f"[bold]{key}:[/bold] {value}")

    console.print()
    print_messages(dataset_line.get("messages", []))
