"""Tests for model publishing without contacting the Hub or training a model."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from huggingface_hub import ModelCard
from mlflow.utils.mlflow_tags import MLFLOW_GIT_BRANCH, MLFLOW_GIT_COMMIT

from satyrn.trainer.unsloth import hub


@pytest.fixture
def training_run(monkeypatch: pytest.MonkeyPatch) -> None:
    run = SimpleNamespace(info=SimpleNamespace(run_id="run-123", experiment_id="42"))
    tags = {MLFLOW_GIT_BRANCH: "main", MLFLOW_GIT_COMMIT: "abc123"}
    hydra_config = SimpleNamespace(
        job=SimpleNamespace(config_name="experiment/python"),
        overrides=SimpleNamespace(task=["model=qwen", "run_name=hello world"]),
    )
    monkeypatch.setattr(hub.mlflow, "active_run", lambda: run)
    monkeypatch.setattr(hub.mlflow, "get_run", lambda run_id: SimpleNamespace(data=SimpleNamespace(tags=tags)))
    monkeypatch.setattr(hub.mlflow, "get_tracking_uri", lambda: "https://mlflow.example/")
    monkeypatch.setattr(hub.HydraConfig, "get", lambda: hydra_config)


def test_publish_both_models_and_preserve_each_card(training_run: None, monkeypatch: pytest.MonkeyPatch) -> None:
    cards = {
        "org/model": ModelCard("---\nlicense: apache-2.0\ntags:\n- merged\n---\n# Merged\n"),
        "org/model-GGUF": ModelCard("---\nbase_model: org/model\ntags:\n- gguf\n---\n# GGUF\n"),
    }
    pushed = {}
    monkeypatch.setattr(hub.ModelCard, "load", lambda repo_id: cards[repo_id])
    monkeypatch.setattr(hub.ModelCard, "push_to_hub", lambda card, repo_id: pushed.update({repo_id: card.content}))
    model = Mock()
    processor = object()
    config = SimpleNamespace(
        push_to_hub_path="org/model", model=SimpleNamespace(name="base/model"), datasets=SimpleNamespace(rl=None)
    )

    hub.upload_to_hub(model, processor, config)

    model.push_to_hub_merged.assert_called_once_with("org/model", processor, save_method="merged_16bit")
    model.push_to_hub_gguf.assert_called_once_with("org/model-GGUF", processor, quantization_method="q4_k_m")
    for repo_id, heading, tag in [("org/model", "# Merged", "merged"), ("org/model-GGUF", "# GGUF", "gguf")]:
        content = pushed[repo_id]
        assert heading in content
        assert cards[repo_id].data.tags == [tag]
        assert "https://mlflow.example/#/experiments/42/runs/run-123" in content
        assert date.today().isoformat() in content
        assert "`experiment/python`" in content
        assert "model=qwen 'run_name=hello world'" in content
        assert "`main`" in content
        assert "`abc123`" in content
        assert f"hf download {repo_id}" in content
        assert f'snapshot_download(repo_id="{repo_id}")' in content
        assert "https://huggingface.co/base/model" in content
        assert "RL dataset stage was disabled" in content
        assert f"https://huggingface.co/{repo_id}" in content
    assert 'model_id = "org/model"' in pushed["org/model"]
    assert "AutoModelForCausalLM" not in pushed["org/model-GGUF"]
    assert "GGUF-compatible" in pushed["org/model-GGUF"]
    assert cards["org/model"].data.license == "apache-2.0"
    assert cards["org/model-GGUF"].data.base_model == "org/model"


def test_card_update_replaces_only_satyrn_section(monkeypatch: pytest.MonkeyPatch) -> None:
    card = ModelCard("---\nlicense: mit\n---\n# Original\n")
    monkeypatch.setattr(hub.ModelCard, "load", lambda repo_id: card)
    push = Mock()
    monkeypatch.setattr(hub.ModelCard, "push_to_hub", push)

    hub.push_model_card("org/model", "Old section")
    card.text += "\n# Additional content\n"
    hub.push_model_card("org/model", "New section")

    assert card.text.count(hub.CARD_START) == 1
    assert "Old section" not in card.text
    assert "New section" in card.text
    assert "# Original" in card.text
    assert "# Additional content" in card.text
    assert card.data.license == "mit"
    assert push.call_args_list == [call("org/model"), call("org/model")]


def test_card_escapes_table_pipes(training_run: None, monkeypatch: pytest.MonkeyPatch) -> None:
    hydra_config = SimpleNamespace(
        job=SimpleNamespace(config_name="experiment/python"),
        overrides=SimpleNamespace(task=["run_name=one|two"]),
    )
    monkeypatch.setattr(hub.HydraConfig, "get", lambda: hydra_config)

    config = SimpleNamespace(model=SimpleNamespace(name="base/model"), datasets=SimpleNamespace(rl=["data.jsonl"]))
    card = hub.render_model_card("org/model", config)
    assert "one\\|two" in card
    assert "RL dataset stage was disabled" not in card
    assert "@misc{satyrn_model," in card


def test_card_links_to_config_at_training_commit(training_run: None, monkeypatch: pytest.MonkeyPatch) -> None:
    run = SimpleNamespace(data=SimpleNamespace(tags={MLFLOW_GIT_COMMIT: "bc2114645471f93f24742aff568c4622526cfca8"}))
    monkeypatch.setattr(hub.mlflow, "get_run", lambda run_id: run)
    monkeypatch.setattr(
        hub.HydraConfig,
        "get",
        lambda: SimpleNamespace(
            job=SimpleNamespace(config_name="experiment/py3.15-qwen3.8-27b"),
            overrides=SimpleNamespace(task=[]),
        ),
    )
    config = SimpleNamespace(model=SimpleNamespace(name="unsloth/Qwen3.8-27B"), datasets=SimpleNamespace(rl=None))

    card = hub.render_model_card("satyrn-ai/Qwen3.8-27B-py3.15", config)

    assert (
        "https://github.com/satyrn-ai/satyrn-models/blob/bc2114645471f93f24742aff568c4622526cfca8/"
        "trainer/unsloth/configs/experiment/py3.15-qwen3.8-27b.yaml"
    ) in card
    assert "@misc{satyrn_qwen3_8_27b_py3_15," in card
