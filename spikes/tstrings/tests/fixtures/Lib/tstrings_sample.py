"""Sample module with known t-string usage for the mining fixture test."""

GREETING = t"Hi"


def greet(name: str) -> str:
    """Greet a user by name."""
    return t"Hello, {name}"


def pair(a: str, b: str) -> tuple[str, str]:
    """Build two templates."""
    first = t"a={a}"
    second = t"b={b}"
    return (first, second)
