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


def print_ideas(ideas: list) -> None:
    """Print ideas as a plain list."""
    console.rule("[bold blue]Ideas[/bold blue]")
    for idea in ideas:
        console.print(f"- {idea.description}", markup=False, highlight=False)
    console.print()


def print_test_cases(test_cases: list[dict]) -> None:
    """Print each test case as its name, input, expected output and test code."""
    console.print(f"[bold]test_cases ({len(test_cases)}):[/bold]")
    for index, test_case in enumerate(test_cases, start=1):
        console.print(f"[bold]{index}. {test_case['name']}[/bold]", markup=True, highlight=False)
        console.print(Markdown(f"input:\n```python\n{test_case['input']}\n```"))
        console.print(Markdown(f"expected output:\n```python\n{test_case['expected_output']}\n```"))
        console.print(Markdown(f"test code:\n```python\n{test_case['test_code']}\n```"))


def print_dataset_line(dataset_line: dict) -> None:
    """Print a dataset line with messages and metadata."""
    console.rule("[bold blue]Dataset Line[/bold blue]")
    fields = ["filename", "python_version", "idea"]
    for key in fields:
        if dataset_line.get(key):
            console.print(f"[bold]{key}:[/bold] {dataset_line[key]}")

    markdown_fields = ["code", "solution", "trace", "expected_output"]
    for key in markdown_fields:
        if dataset_line.get(key):
            console.print(f"[bold]{key}:[/bold]")
            text = f"```python\n{dataset_line[key]}\n```" if key in ("code", "solution") else dataset_line[key]
            console.print(Markdown(text))

    if dataset_line.get("test_cases"):
        print_test_cases(dataset_line["test_cases"])

    known_keys = set(fields) | set(markdown_fields) | {"prompt", "completion", "test_cases"}
    for key, value in dataset_line.items():
        if key not in known_keys and value:
            console.print(f"[bold]{key}:[/bold] {value}")

    console.print()
    prompt = dataset_line.get("prompt", [])
    messages = list(prompt) if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
    messages += dataset_line.get("completion", [])
    print_messages(messages)
