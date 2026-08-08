"""CheckSpec: the closed, declarative observation union.

A ``CheckSpec`` declares *what to observe*, never *what the answer is*. The
provider runs the reference program under the verifying interpreter and
materializes the comparison observation internally (Task 2). There is therefore
no field on any check variant that carries a caller-asserted expected value,
and the union is closed: a producer cannot invent a check kind or attach an
arbitrary source expression. Unknown keys on any check are rejected, which is
how a smuggled ``expected`` value is caught.

The union is intentionally small for Task 1 and is the seam Task 2 materializes:

- ``NameEquals``: after execution, the candidate's namespace binding for
  ``name`` must equal the reference's binding for the same ``name``. This is
  the comparison observation; both sides are provider-derived.
- ``Raises``: executing the program must raise an exception of a whitelisted
  built-in type. The exception type is an observation spec, not a trusted
  expected *value* of the result.
"""

from __future__ import annotations

import dataclasses
import keyword
from typing import Any, Literal

from ._common import ContractError, reject_unknown_keys, require_object

NAME_EQUALS = "name_equals"
RAISES = "raises"

# Whitelisted exception class names. All are builtins, so a check can name a
# type without importing anything executable or reaching attribute access that
# could hide a side effect. Adding a non-builtin exception is a contract
# change, not a free parameter.
_ALLOWED_EXCEPTIONS = frozenset(
    {
        "AttributeError",
        "IndexError",
        "KeyError",
        "NameError",
        "RuntimeError",
        "SyntaxError",
        "TypeError",
        "ValueError",
        "ZeroDivisionError",
        "FileNotFoundError",
        "PermissionError",
    }
)


def _require_identifier(value: object, what: str) -> str:
    if (
        not isinstance(value, str)
        or not value.isidentifier()
        or keyword.iskeyword(value)
    ):
        raise ContractError(f"{what} must be a valid python identifier, got {value!r}")
    return value


@dataclasses.dataclass(frozen=True, kw_only=True)
class NameEquals:
    """The candidate's namespace binding for ``name`` equals the reference's."""

    kind: Literal["name_equals"] = dataclasses.field(default=NAME_EQUALS)
    name: str

    @classmethod
    def from_dict(cls, data: object) -> NameEquals:
        data = require_object(data, "check")
        reject_unknown_keys(data, frozenset({"kind", "name"}), "name_equals check")
        if "name" not in data:
            raise ContractError("name_equals check missing 'name'")
        return cls(name=_require_identifier(data["name"], "name_equals check name"))

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "name": self.name}


@dataclasses.dataclass(frozen=True, kw_only=True)
class Raises:
    """Executing the program must raise a whitelisted built-in exception type."""

    kind: Literal["raises"] = dataclasses.field(default=RAISES)
    exception: str

    @classmethod
    def from_dict(cls, data: object) -> Raises:
        data = require_object(data, "check")
        reject_unknown_keys(data, frozenset({"kind", "exception"}), "raises check")
        if "exception" not in data:
            raise ContractError("raises check missing 'exception'")
        exception = data["exception"]
        if (
            not isinstance(exception, str)
            or "." in exception
            or not exception.isidentifier()
        ):
            raise ContractError(
                f"raises check exception must be a builtin name, got {exception!r}"
            )
        if exception not in _ALLOWED_EXCEPTIONS:
            raise ContractError(f"raises check exception not allowed: {exception!r}")
        return cls(exception=exception)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "exception": self.exception}


CheckSpec = NameEquals | Raises


def check_from_dict(data: object) -> CheckSpec:
    d = require_object(data, "check")
    if "kind" not in d:
        raise ContractError("check must be an object with a 'kind'")
    kind = d["kind"]
    if kind == NAME_EQUALS:
        return NameEquals.from_dict(d)
    if kind == RAISES:
        return Raises.from_dict(d)
    raise ContractError(f"unknown check kind: {kind!r}")


def checks_from_list(data: object) -> tuple[CheckSpec, ...]:
    if not isinstance(data, list) or not data:
        raise ContractError("task 'checks' must be a non-empty list")
    return tuple(check_from_dict(item) for item in data)


__all__ = [
    "NAME_EQUALS",
    "RAISES",
    "NameEquals",
    "Raises",
    "CheckSpec",
    "check_from_dict",
    "checks_from_list",
]
