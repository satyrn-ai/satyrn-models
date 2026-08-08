"""Contract version constants for dataset and execution.

The dataset contract version governs the wire shape of a ``DatasetSnapshot``:
its manifest, task records, checks, policy references, completion mode, and
provenance. The execution contract version governs the subprocess protocol that
materializes reference observations (Task 2). A snapshot pins both at ingest;
either drift is a hard rejection, never a silent migration.
"""

DATASET_CONTRACT_VERSION = "1"
EXECUTION_CONTRACT_VERSION = "1"

__all__ = ["DATASET_CONTRACT_VERSION", "EXECUTION_CONTRACT_VERSION"]
