"""GRPO reward functions."""

from satyrn.trainer.unsloth.rl.code_tester import TestCase, find_code, score_version_specific_code


def reward_correct_code(
    completions: list[list[dict[str, str]]],
    test_cases: list[list[dict]],
    metadata: list[dict],
    **kwargs,
) -> list[float]:
    """Return each completion's score on its target Python version."""
    rewards = []
    for completion, row_test_cases, row_metadata in zip(completions, test_cases, metadata, strict=True):
        answer_code = find_code(completion[-1]["content"])
        cases = [TestCase(name=case["name"], test_code=case["test_code"]) for case in row_test_cases]
        score = score_version_specific_code(answer_code, cases, row_metadata["python_version"])
        rewards.append(score)
    return rewards
