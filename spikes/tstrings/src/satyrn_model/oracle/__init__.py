"""Candidate oracle: verification and anti-vacuity task qualification."""

from .qualify import (
    QualificationOutcome,
    Qualified,
    VacuityUntested,
    qualify_task,
)
from .verify import (
    VerificationOutcome,
    VerifyAccepted,
    verify_candidate,
)

__all__ = [
    "QualificationOutcome",
    "Qualified",
    "VacuityUntested",
    "VerificationOutcome",
    "VerifyAccepted",
    "qualify_task",
    "verify_candidate",
]
