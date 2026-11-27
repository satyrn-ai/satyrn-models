"""Combined eval scores."""


def satyrn_models_score(python_eval: float, human_eval: float) -> float:
    """Return the weighted average of the PythonEval and HumanEval accuracies."""
    return (2 * python_eval + human_eval) / 3
