"""Tests for the Cycle 6.1 evaluation scorer helpers."""

import json
import sys
from pathlib import Path

from click.testing import CliRunner

from satyrn.tstrings.eval import (
    _adapter_tiers,
    _load_model,
    _reference_targets,
    _Tier,
    extract_code,
    generate,
    load_reference_scores,
    reproduce,
    reproduce_cmd,
    score_completion,
    score_results,
)


def test_extract_code_fenced_python_block() -> None:
    """Extract the interior of a language-tagged fenced block."""
    completion = "```python\nx = 1\nprint(x)\n```\n"
    assert extract_code(completion) == "x = 1\nprint(x)"


def test_extract_code_bare_fence_after_prose() -> None:
    """Strip leading prose and extract the interior of a bare fence."""
    completion = "Here is my code:\n```\nprint('hi')\n```\n"
    assert extract_code(completion) == "print('hi')"


def test_extract_code_no_fence_returns_stripped() -> None:
    """Return the whole completion stripped when no fence is present."""
    completion = "x = 1\nprint(x)\n"
    assert extract_code(completion) == "x = 1\nprint(x)"


def test_extract_code_takes_last_fenced_block() -> None:
    """Keep only the last fenced block when several are present."""
    completion = "```python\na = 1\n```\n```python\nb = 2\n```\n"
    assert extract_code(completion) == "b = 2"


def test_extract_code_strips_think_and_end_tokens() -> None:
    """Drop the reasoning trace and chat end markers."""
    completion = "<think>reasoning</think>\nprint(1)\n<|im_end|>\n"
    assert extract_code(completion) == "\nprint(1)"


def test_extract_code_truncates_to_longest_compiling_prefix() -> None:
    """Drop trailing lines until the remainder compiles."""
    completion = "print('ok')\ntrailing garbage !!!"
    assert extract_code(completion) == "print('ok')"


def test_extract_code_unterminated_fence_stays_raw() -> None:
    """An unterminated fence leaves the raw text for the parse stage to reject."""
    completion = "```python\nx = 1"
    assert extract_code(completion) == "```python\nx = 1"


_REFERENCE = 'city = "Boston"\ntmpl = t"Weather in {city} today"\nskeleton = "".join(tmpl.strings)\n'

_GOOD_CANDIDATE = (
    "from string.templatelib import Template\n"
    'city = "Boston"\n'
    'tmpl = t"Weather in {city} today"\n'
    'skeleton = "".join(tmpl.strings)\n'
)


def _task(reference: str = _REFERENCE) -> dict:
    """Return a benchmark-shaped task checking the skeleton name."""
    return {
        "id": "task-1",
        "prompt": "build a t-string and join its .strings into skeleton",
        "reference": reference,
        "checks": [{"kind": "name_equals", "name": "skeleton"}],
        "completion": {"mode": "complete_program"},
        "policy": {
            "id": "tstring",
            "config": {"requires_template": True, "templatelib_apis": ["strings", "values"]},
        },
        "provenance": {},
    }


def test_score_completion_correct_with_mechanism() -> None:
    """A t-string candidate matching the reference passes both checks."""
    result = score_completion(_GOOD_CANDIDATE, _task())
    assert result["passed"] is True
    assert result["policy_passed"] is True
    assert result["stage"] is None
    assert result["reason"] is None
    assert result["candidate"] == _GOOD_CANDIDATE.strip()


def test_score_completion_correct_without_mechanism() -> None:
    """An f-string candidate with the right value passes correctness only."""
    candidate = (
        'city = "Boston"\ntemplate = f"Weather in {city} today"\nskeleton = "".join(["Weather in ", " today"])\n'
    )
    result = score_completion(candidate, _task())
    assert result["passed"] is True
    assert result["policy_passed"] is False
    assert result["stage"] == "policy"
    assert "t-string" in result["reason"]


def test_score_completion_incorrect_with_mechanism() -> None:
    """A t-string candidate with the wrong value fails correctness."""
    candidate = (
        "from string.templatelib import Template\n"
        'city = "Boston"\n'
        'tmpl = t"Weather in {city} today"\n'
        'skeleton = "".join(["nope"])\n'
    )
    result = score_completion(candidate, _task())
    assert result["passed"] is False
    assert result["stage"] == "semantic_check"


def test_score_completion_unparseable() -> None:
    """A candidate that cannot parse fails at the candidate_parse stage."""
    result = score_completion("x =", _task())
    assert result["passed"] is False
    assert result["stage"] == "candidate_parse"


def _second_good_candidate() -> str:
    """Return a second t-string candidate matching the reference value."""
    return (
        "from string.templatelib import Template\n"
        'city = "Boston"\n'
        'tmpl = t"Weather in {city} today"\n'
        'skeleton = "".join(tmpl.strings)\n'
    )


def test_score_results_aggregates_summary_and_failure_stages() -> None:
    """Aggregate correctness vs mechanism counts and bucket failures by stage."""
    completions = [
        _GOOD_CANDIDATE,
        _second_good_candidate(),
        "x =",
        'city = "Boston"\ntemplate = f"Weather in {city} today"\nskeleton = "".join(["Weather in ", " today"])\n',
    ]
    tasks = [_task() for _ in completions]
    output = score_results(completions, tasks)
    summary = output["summary"]
    assert summary["passed"] == 3
    assert summary["total"] == 4
    assert summary["score"] == 0.5
    assert summary["failure_stages"] == {"candidate_parse": 1, "policy": 1}
    reference_keys = {
        "candidate",
        "completion",
        "elapsed",
        "id",
        "passed",
        "policy_passed",
        "prompt",
        "reason",
        "reference",
        "stage",
    }
    for result in output["results"]:
        assert set(result) == reference_keys


def test_load_reference_scores_reads_summary_score_keyed_by_stem(tmp_path) -> None:
    """Read each file's summary score keyed by its filename stem."""
    path = tmp_path / "eval-v2-base.json"
    path.write_text('{"summary": {"score": 0.05, "total": 100}, "results": []}\n')
    assert load_reference_scores([path]) == {"eval-v2-base": 0.05}


def _set_tasks() -> list[dict]:
    """Return the benchmark tasks whose reference builds a set or frozenset."""
    path = Path(__file__).resolve().parents[1] / "benchmark" / "ood-v2" / "tasks.jsonl"
    tasks = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [task for task in tasks if "set(" in task["reference"] or "frozenset" in task["reference"]]


def test_set_comparing_tasks_score_identically_across_runs() -> None:
    """Set-valued benchmark tasks score identically across repeated runs."""
    tasks = _set_tasks()
    assert len(tasks) == 2
    for task in tasks:
        completion = task["reference"]
        first = score_completion(completion, task)
        second = score_completion(completion, task)
        assert first["passed"] is True
        assert first["policy_passed"] is True
        assert first == second


class _SampleUtils:
    """Record make_sampler calls and return a sentinel sampler."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def make_sampler(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return "sampler"


class _FakeMLXLM:
    """Record mlx_lm.load/generate and make_sampler calls for a canned completion."""

    def __init__(self) -> None:
        self.load_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.generate_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.sample_utils = _SampleUtils()

    def load(self, *args: object, **kwargs: object) -> tuple[str, str]:
        self.load_calls.append((args, kwargs))
        return ("loaded-model", "loaded-tokenizer")

    def generate(self, *args: object, **kwargs: object) -> str:
        self.generate_calls.append((args, kwargs))
        return "generated response"


def test_load_model_base_has_no_adapter(monkeypatch) -> None:
    """Loading without an adapter forwards adapter_path=None to mlx_lm.load."""
    fake = _FakeMLXLM()
    monkeypatch.setitem(sys.modules, "mlx_lm", fake)
    loaded, tokenizer = _load_model("mlx-community/test")
    assert (loaded, tokenizer) == ("loaded-model", "loaded-tokenizer")
    (model,), load_kwargs = fake.load_calls[0]
    assert model == "mlx-community/test"
    assert load_kwargs["adapter_path"] is None
    assert fake.generate_calls == []


def test_load_model_passes_adapter_path(monkeypatch, tmp_path: Path) -> None:
    """Loading with an adapter forwards its path to mlx_lm.load."""
    fake = _FakeMLXLM()
    monkeypatch.setitem(sys.modules, "mlx_lm", fake)
    adapter = tmp_path / "adapter.safetensors"
    adapter.touch()
    loaded, tokenizer = _load_model("mlx-community/test", adapter)
    assert (loaded, tokenizer) == ("loaded-model", "loaded-tokenizer")
    (model,), load_kwargs = fake.load_calls[0]
    assert model == "mlx-community/test"
    assert load_kwargs["adapter_path"] == str(adapter)
    assert fake.generate_calls == []


def test_generate_base_arm_generates_greedily(monkeypatch) -> None:
    """Generate builds the system+prompt text and samples with a temp-0 sampler."""
    fake = _FakeMLXLM()
    monkeypatch.setitem(sys.modules, "mlx_lm", fake)
    text = generate(
        "Build a t-string",
        model="loaded-model",
        tokenizer="loaded-tokenizer",
        system_prompt="Be precise.",
    )
    assert text == "generated response"
    assert fake.load_calls == []
    assert fake.sample_utils.calls == [{"temp": 0.0}]
    (loaded, tokenizer, prompt), gen_kwargs = fake.generate_calls[0]
    assert (loaded, tokenizer) == ("loaded-model", "loaded-tokenizer")
    assert gen_kwargs["max_tokens"] == 700
    assert gen_kwargs["sampler"] == "sampler"
    assert "Be precise." in prompt
    assert prompt.endswith("Build a t-string")


def test_generate_docs_arm_prepends_docs_block(monkeypatch) -> None:
    """The docs arm prepends the docs block before the task prompt."""
    fake = _FakeMLXLM()
    monkeypatch.setitem(sys.modules, "mlx_lm", fake)
    docs = "# PEP 750 documentation context\nTemplate string literals..."
    generate(
        "Build a t-string",
        model="loaded-model",
        tokenizer="loaded-tokenizer",
        docs=docs,
        system_prompt="Be precise.",
    )
    assert fake.load_calls == []
    (loaded, tokenizer, prompt), gen_kwargs = fake.generate_calls[0]
    assert (loaded, tokenizer) == ("loaded-model", "loaded-tokenizer")
    assert fake.sample_utils.calls == [{"temp": 0.0}]
    assert gen_kwargs["sampler"] == "sampler"
    assert "Be precise." in prompt
    assert docs in prompt
    assert prompt.index(docs) < prompt.index("Build a t-string")


def _tiers() -> list[_Tier]:
    """Return the three reference reproduction tiers."""
    return [
        _Tier("base", 0.05, "mlx-community/test"),
        _Tier("docs", 0.61, "mlx-community/test", docs=True),
        _Tier("adapter", (0.47, 0.58), "mlx-community/test", adapter_path=Path("adapter")),
    ]


def _loaded(model: str, adapter_path: Path | None) -> tuple[str, str]:
    """Return a fake loaded model/tokenizer pair, ignoring the load inputs."""
    return ("loaded-model", "loaded-tokenizer")


def test_reproduce_within_tolerance_passes(monkeypatch) -> None:
    """Scores inside ±0.03 of each target report PASS without warnings."""
    monkeypatch.setattr(
        "satyrn.tstrings.eval.generate",
        lambda *a, **k: "ok",
    )
    scores = iter([0.05, 0.61, 0.52])
    monkeypatch.setattr(
        "satyrn.tstrings.eval.score_results",
        lambda completions, tasks: {"summary": {"score": next(scores)}},
    )
    report = reproduce([_task()], _tiers(), system_prompt="Be precise.", load_fn=_loaded)
    assert [tier["passed"] for tier in report["tiers"]] == [True, True, True]
    assert report["warnings"] == []


def test_reproduce_out_of_tolerance_warns(monkeypatch) -> None:
    """A score more than ±0.03 from its target reports FAIL and a warning."""
    monkeypatch.setattr(
        "satyrn.tstrings.eval.generate",
        lambda *a, **k: "ok",
    )
    monkeypatch.setattr(
        "satyrn.tstrings.eval.score_results",
        lambda completions, tasks: {"summary": {"score": 0.5}},
    )
    report = reproduce([_task()], _tiers(), system_prompt="Be precise.", load_fn=_loaded)
    assert [tier["passed"] for tier in report["tiers"]] == [False, False, True]
    assert len(report["warnings"]) == 2
    assert "base: 0.5 outside 0.05 ± 0.03" in report["warnings"][0]
    assert "docs: 0.5 outside 0.61 ± 0.03" in report["warnings"][1]


def test_reproduce_scores_fake_completions_per_tier(monkeypatch) -> None:
    """The real scorer maps each arm's fixed completions to its expected score."""
    monkeypatch.setattr(
        "satyrn.tstrings.eval.generate",
        lambda prompt, *, model, tokenizer, docs, system_prompt: "generated",
    )
    report = reproduce([_task()], _tiers(), system_prompt="Be precise.", load_fn=_loaded)
    assert [tier["passed"] for tier in report["tiers"]] == [False, False, False]
    assert report["warnings"]


def test_reproduce_loads_model_once_per_tier(monkeypatch) -> None:
    """The model is loaded once per tier, then reused across all its tasks."""
    loads: list[tuple[str, Path | None]] = []
    monkeypatch.setattr(
        "satyrn.tstrings.eval.generate",
        lambda prompt, *, model, tokenizer, docs, system_prompt: "generated",
    )
    monkeypatch.setattr(
        "satyrn.tstrings.eval.score_results",
        lambda completions, tasks: {"summary": {"score": 0.5}},
    )

    def load_fn(model: str, adapter_path: Path | None) -> tuple[str, str]:
        loads.append((model, adapter_path))
        return ("loaded-model", "loaded-tokenizer")

    reproduce([_task(), _task()], _tiers(), system_prompt="Be precise.", load_fn=load_fn)
    assert loads == [
        ("mlx-community/test", None),
        ("mlx-community/test", None),
        ("mlx-community/test", Path("adapter")),
    ]


def test_load_reference_scores_matches_inherited_targets() -> None:
    """The committed reference files carry the BRIEF targets (0.05/0.61/0.47-0.58)."""
    results_dir = Path(__file__).resolve().parents[1] / "results"
    files = [
        results_dir / "eval-v2-base.json",
        results_dir / "eval-v2-base-docs.json",
        results_dir / "eval-v2-runA-seed43.json",
    ]
    scores = load_reference_scores(files)
    assert scores["eval-v2-base"] == 0.05
    assert scores["eval-v2-base-docs"] == 0.61
    assert 0.47 <= scores["eval-v2-runA-seed43"] <= 0.58


def test_reproduce_cli_runs_three_tiers_and_writes_report(monkeypatch, tmp_path: Path) -> None:
    """The reproduce command scores base/docs/adapter tiers and writes a markdown report."""
    adapter_dir = tmp_path / "adapters"
    (adapter_dir / "m2i-runA-seed43").mkdir(parents=True)
    output_dir = tmp_path / "reports"

    batch_sizes: list[int] = []
    monkeypatch.setattr(
        "satyrn.tstrings.eval.generate",
        lambda prompt, *, model, tokenizer, docs, system_prompt: "generated",
    )
    monkeypatch.setattr(
        "satyrn.tstrings.eval._load_model",
        lambda model, adapter_path: ("loaded-model", "loaded-tokenizer"),
    )

    def fake_score(completions: list[str], tasks: list[dict]) -> dict:
        batch_sizes.append(len(completions))
        return {"summary": {"score": 0.5}}

    monkeypatch.setattr("satyrn.tstrings.eval.score_results", fake_score)

    result = CliRunner().invoke(
        reproduce_cmd,
        ["--adapter-dir", str(adapter_dir), "-o", str(output_dir)],
    )

    assert result.exit_code == 0, result.output
    assert batch_sizes == [100, 100, 100]
    report_path = output_dir / "reproduction.md"
    assert report_path.exists()
    text = report_path.read_text()
    assert "base" in text
    assert "docs" in text
    assert "adapter-m2i-runA-seed43" in text
    assert "0.52" in text
    assert "FAIL" in text
    assert "PASS" in text
    assert "warning:" in result.output


def test_reference_targets_excludes_docs_files(tmp_path: Path) -> None:
    """Seed result files with a -docs suffix are not read as adapter targets."""
    (tmp_path / "eval-v2-runA-seed43.json").write_text('{"summary": {"score": 0.5}}')
    (tmp_path / "eval-v2-runA-seed43-docs.json").write_text('{"summary": {"score": 0.9}}')
    (tmp_path / "eval-v2-runA-seed44.json").write_text('{"summary": {"score": 0.6}}')
    (tmp_path / "eval-v2-runA-docs.json").write_text('{"summary": {"score": 0.8}}')
    assert _reference_targets(tmp_path) == {"43": 0.5, "44": 0.6}


def test_adapter_tiers_ignores_docs_target_keys(tmp_path: Path) -> None:
    """Only seed-suffixed adapters become tiers; a -docs target key never does."""
    adapter_dir = tmp_path / "adapters"
    (adapter_dir / "m2i-runA-seed43").mkdir(parents=True)
    (adapter_dir / "m2i-runA-seed43-docs").mkdir(parents=True)
    targets = {"43": 0.5, "43-docs": 0.9}
    tiers = _adapter_tiers(adapter_dir, "mlx-community/test", targets)
    assert [tier.name for tier in tiers] == ["adapter-m2i-runA-seed43"]


def test_reproduce_cli_missing_adapters_exits_nonzero(tmp_path: Path) -> None:
    """A missing adapter dir fails loudly instead of silently reporting base+docs only."""
    adapter_dir = tmp_path / "adapters"  # does not exist
    output_dir = tmp_path / "reports"
    result = CliRunner().invoke(
        reproduce_cmd,
        ["--adapter-dir", str(adapter_dir), "-o", str(output_dir)],
    )
    assert result.exit_code == 1
    assert "adapter" in result.output.lower()
    assert not (output_dir / "reproduction.md").exists()


def test_evaluate_arms_scores_all_arms_with_same_harness() -> None:
    """evaluate_arms scores base, docs, and every adapter with one harness."""
    from satyrn.tstrings.eval import evaluate_arms

    tasks = [{"prompt": "p1", "id": "1"}, {"prompt": "p2", "id": "2"}]
    calls: list[tuple[str | None, str | None]] = []

    def fake_generate(prompt, *, system_prompt, docs, adapter_path):
        calls.append((docs, adapter_path.name if adapter_path else None))
        return "x = 1\n"

    def fake_score(completions, benchmark):
        return {"summary": {"score": 0.5}}

    adapter_paths = [Path("seed1"), Path("seed2")]
    arms = evaluate_arms(
        tasks,
        system_prompt="sys",
        docs_block="docs",
        adapter_paths=adapter_paths,
        generate_fn=fake_generate,
        score_fn=fake_score,
    )
    assert arms["base"] == 0.5 and arms["docs"] == 0.5
    assert arms["adapter:seed1"] == 0.5 and arms["adapter:seed2"] == 0.5
    docs_calls = [(d, a) for d, a in calls if d is not None]
    assert len(docs_calls) == 2  # one docs completion per task


def test_write_report_positive_verdict(tmp_path: Path) -> None:
    """A positive fixture writes 'decision rule met — POSITIVE' with mean+spread."""
    from satyrn.tstrings.eval import write_report

    arms = {"base": 0.05, "docs": 0.60, "adapter:seed1": 0.64, "adapter:seed2": 0.66}
    path = tmp_path / "REPORT.md"
    write_report(arms, adapter_keys=["adapter:seed1", "adapter:seed2"], path=path)
    text = path.read_text()
    assert "decision rule met — POSITIVE" in text
    assert "0.650" in text and "0.64" in text and "0.66" in text


def test_write_report_negative_verdict(tmp_path: Path) -> None:
    """A negative fixture writes 'NEGATIVE' plainly."""
    from satyrn.tstrings.eval import write_report

    arms = {"base": 0.05, "docs": 0.60, "adapter:seed1": 0.55, "adapter:seed2": 0.56}
    path = tmp_path / "REPORT.md"
    write_report(arms, adapter_keys=["adapter:seed1", "adapter:seed2"], path=path)
    assert "decision rule not met — NEGATIVE" in path.read_text()


def test_eval_command_writes_report(monkeypatch, tmp_path: Path) -> None:
    """The eval command scores all arms and writes REPORT.md."""
    from click.testing import CliRunner

    from satyrn.tstrings import eval as eval_module

    monkeypatch.setattr(eval_module, "_load_model", lambda model, adapter_path: ("m", "t"))
    monkeypatch.setattr(
        eval_module,
        "generate",
        lambda prompt, *, model, tokenizer, docs, system_prompt: "x = 1\n",
    )
    monkeypatch.setattr(
        eval_module,
        "score_results",
        lambda completions, tasks: {"summary": {"score": 0.5}},
    )
    monkeypatch.setattr(
        eval_module,
        "_load_jsonl_tasks",
        lambda path: [{"prompt": "p", "id": "1"}],
    )
    bench = tmp_path / "bench.jsonl"
    bench.write_text("{}")
    adapter_dir = tmp_path / "adapters"
    (adapter_dir / "seed1").mkdir(parents=True)
    (adapter_dir / "seed1" / "adapters.safetensors").write_text("x")

    result = CliRunner().invoke(
        eval_module.main,
        ["-i", str(tmp_path / "bench.jsonl"), "-o", str(tmp_path / "reports"), "--adapter-dir", str(adapter_dir)],
    )
    assert result.exit_code == 0, result.output
    report = (tmp_path / "reports" / "REPORT.md").read_text()
    assert "decision rule" in report
