"""Reading the eval JSONL sets into a MemoryDataset."""

from inspect_ai.dataset import MemoryDataset

from satyrn.trainer.unsloth.eval.python_eval import EVAL_SETS, load_dataset


def test_loads_eval_sets() -> None:
    """Every row becomes a Sample with a unique id and the metadata the scorer reads."""
    dataset = load_dataset(EVAL_SETS)

    assert isinstance(dataset, MemoryDataset)
    assert len(dataset) > 0

    ids = [sample.id for sample in dataset]
    assert len(ids) == len(set(ids))

    for sample in dataset:
        assert sample.input and sample.target
        assert sample.metadata["test_cases"]
        assert sample.metadata["python_version"]
        assert sample.metadata["pep"]
