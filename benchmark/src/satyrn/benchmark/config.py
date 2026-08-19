from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelConfig:
    hf_ref: str
    # None matches the checkpoint's native precision. Override with
    # f32 | f16 | bf16 | q8_0 (quantized) | tq1_0 | tq2_0.
    gguf_outtype: str | None = None


MODELS = {
    "mellum2-12b-a2.5": ModelConfig(hf_ref="hf.co/JetBrains/Mellum2-12B-A2.5B-Instruct"),
    "qwen3.6-27b": ModelConfig(hf_ref="hf.co/Qwen/Qwen3.6-27B"),
    "gemma-4-26b-a4b-it": ModelConfig(hf_ref="hf.co/google/gemma-4-26B-A4B-it"),
}

DATASETS = ("humaneval", "mbpp")


@dataclass(frozen=True)
class EvalplusConfig:
    datasets: tuple[str, ...] = DATASETS
    greedy: bool = True
    backend: str = "openai"
    base_url: str = "http://localhost:11434/v1"


@dataclass(frozen=True)
class BenchmarkConfig:
    model: ModelConfig
    results_dir: str = "results/evalplus"
    work_dir: str = ".benchmark_work"
    install_deps: bool = True
    evalplus: EvalplusConfig = field(default_factory=EvalplusConfig)
