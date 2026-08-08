"""Versioned dataset and policy contracts for the satyrn-model provider.

This package publishes the wire types a dataset producer may ship and the
validation ingest performs. It is deliberately the *only* public surface a
producer touches; reference execution (Task 2), the oracle (Task 3), and the
trusted policy registry implementation (Task 3) build on top of these.
"""

from ._common import ContractError
from .checks import CheckSpec, NameEquals, Raises, check_from_dict, checks_from_list
from .completion import CompleteProgram, CompletionSpec, completion_from_dict
from .policy import FeaturePolicy, PolicyRef, PolicyRegistry, PolicyResult
from .provenance import (
    GeneratedProvenance,
    HarvestedProvenance,
    Provenance,
    provenance_from_dict,
)
from .snapshot import (
    DatasetSnapshot,
    Manifest,
    dump_snapshot,
    ingest_snapshot,
    load_snapshot,
)
from .task import TaskRecord, content_id, semantic_content_id
from .versions import DATASET_CONTRACT_VERSION, EXECUTION_CONTRACT_VERSION

__all__ = [
    "DATASET_CONTRACT_VERSION",
    "EXECUTION_CONTRACT_VERSION",
    "ContractError",
    "CheckSpec",
    "NameEquals",
    "Raises",
    "check_from_dict",
    "checks_from_list",
    "CompleteProgram",
    "CompletionSpec",
    "completion_from_dict",
    "FeaturePolicy",
    "PolicyRef",
    "PolicyRegistry",
    "PolicyResult",
    "PolicyRegistry",
    "GeneratedProvenance",
    "HarvestedProvenance",
    "Provenance",
    "provenance_from_dict",
    "DatasetSnapshot",
    "Manifest",
    "dump_snapshot",
    "ingest_snapshot",
    "load_snapshot",
    "TaskRecord",
    "content_id",
    "semantic_content_id",
]
