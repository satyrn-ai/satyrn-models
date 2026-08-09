"""SP5 pattern authoring: registry, approvals, and reviewed catalog."""

from .approvals import (
    ApprovalError,
    PatternApproval,
    audit_pattern,
    read_approvals,
    require_approval,
    write_approvals,
)
from .catalog import CATALOG
from .registry import (
    Pattern,
    PatternRegistry,
    PatternValidationError,
    PropertySpec,
    build_properties,
    classify,
    pattern_arity,
    pattern_input_fingerprint,
    validate_pattern,
)

__all__ = [
    "ApprovalError",
    "CATALOG",
    "Pattern",
    "PatternApproval",
    "PatternRegistry",
    "PatternValidationError",
    "PropertySpec",
    "audit_pattern",
    "build_properties",
    "classify",
    "pattern_arity",
    "pattern_input_fingerprint",
    "read_approvals",
    "require_approval",
    "validate_pattern",
    "write_approvals",
]
