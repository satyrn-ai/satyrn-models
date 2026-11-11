from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelConfig:
    hf_ref: str
    # None matches the checkpoint's native precision. Override with
    # f32 | f16 | bf16 | q8_0 (quantized) | tq1_0 | tq2_0.
    gguf_outtype: str | None = None


DATASETS = ("humaneval", "mbpp")


@dataclass(frozen=True)
class EvalplusConfig:
    datasets: tuple[str, ...] = DATASETS
    greedy: bool = True
    # evalplus resets it to 1 for greedy decoding
    nsamples: int = 1
    temperature: float = 0.0
    backend: str = "openai"
    base_url: str = "http://localhost:11434/v1"

    def __post_init__(self) -> None:
        if not self.greedy and self.temperature <= 0:
            raise ValueError("Sampling needs a positive temperature; pass --temperature or keep --greedy.")


@dataclass(frozen=True)
class BenchmarkConfig:
    model: ModelConfig
    results_dir: str = "results/evalplus"
    work_dir: str = ".benchmark_work"
    install_deps: bool = True
    evalplus: EvalplusConfig = field(default_factory=EvalplusConfig)
