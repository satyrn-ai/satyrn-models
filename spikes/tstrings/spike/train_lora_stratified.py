"""Run mlx-lm LoRA with stratum-diverse rather than length-homogeneous batches.

Three batch orderings are available so repair step 5's comparison can be run
on repaired data:

``interleaved``
    Deterministic construction of batches that span role x capability x
    prompt-family strata. This is the default and the step-5 replacement.
``shuffled``
    An ordinary permutation. The baseline interleaving must beat.
``operation``
    The superseded ordering, which guaranteed eight distinct *operations* per
    batch. It is retained only so the reviewed run stays reproducible: an
    operation is coarser than a stratum, so it freely mixed author and
    consumer goals inside one batch.

All three cover every row exactly once per epoch and pad only the final short
batch.
"""

import argparse
import collections
import functools
import json
import sys
from collections import defaultdict
from pathlib import Path

import mlx.core as mx
import numpy as np
from mlx_lm.tuner.trainer import iterate_batches as mlx_iterate_batches

BATCHINGS = ("interleaved", "shuffled", "operation")


def _pad_final(
    batches: list[list[int]], batch_size: int, rng: np.random.Generator
) -> list[list[int]]:
    """Top up the last short batch from rows already drawn this epoch.

    The superseded batcher instead stopped once fewer than ``batch_size`` rows
    remained, so 450 rows at batch size 8 covered 448 — and because buckets
    were reshuffled per epoch, a *different* pair was withheld each time.
    """
    remainder = batches[-1]
    if len(remainder) < batch_size:
        pool = [index for batch in batches[:-1] for index in batch]
        padding = rng.choice(pool, size=batch_size - len(remainder), replace=False)
        remainder.extend(int(index) for index in padding)
    return batches


def _chunk(order: list[int], batch_size: int) -> list[list[int]]:
    return [
        order[start : start + batch_size] for start in range(0, len(order), batch_size)
    ]


def _interleaved_indices(
    strata: list[str], batch_size: int, rng: np.random.Generator
) -> list[list[int]]:
    """Build batches that span distinct strata and hold the global role share.

    Operation-uniqueness guaranteed eight distinct operations but nothing
    about role or prompt family, so one batch could hold eight author rows in
    a single wording.

    Two orderings were tried and measured before this one. Plain round-robin
    over live strata drains the small strata first, so the tail of the epoch
    collapses onto whichever strata are deepest — 19 single-role batches out
    of 57 on a curriculum with few, deep author strata. Placing each stratum's
    rows at even fractional positions across the epoch fixed the tail but
    clumped equal-span strata together, giving 15 single-role batches on the
    real handoff.

    Batches are therefore built directly rather than by ordering and chunking.
    Each pick prefers, in order: a stratum not yet in this batch; the role
    furthest below its share of the whole split; the stratum with the most
    rows left; then a stable role-alternating rank. Largest-first keeps every
    stratum alive to roughly the same point in the epoch, which removes the
    tail collapse, and the role term stops a role-correlated depth imbalance
    from reintroducing it.

    Single-role batches can still occur once a role is exhausted, but only in
    the final batches of an epoch — never scattered through it, as shuffling
    produces them.
    """
    buckets: dict[str, list[int]] = defaultdict(list)
    for index, stratum in enumerate(strata):
        buckets[stratum].append(index)
    for indices in buckets.values():
        rng.shuffle(indices)

    tie_break = {
        key: rank for rank, key in enumerate(_interleave_roles(sorted(buckets)))
    }
    role_share = collections.Counter(key.split("|")[0] for key in strata)
    total = len(strata)

    batches: list[list[int]] = []
    while any(buckets.values()):
        batch: list[int] = []
        used: set[str] = set()
        roles: collections.Counter[str] = collections.Counter()
        while len(batch) < batch_size and any(buckets.values()):
            key = min(
                (key for key, rows in buckets.items() if rows),
                key=lambda key: (
                    key in used,
                    (roles[key.split("|")[0]] + 1)
                    / (role_share[key.split("|")[0]] / total),
                    -len(buckets[key]),
                    tie_break[key],
                ),
            )
            batch.append(buckets[key].pop())
            used.add(key)
            roles[key.split("|")[0]] += 1
        batches.append(batch)
    return _pad_final(batches, batch_size, rng)


def _interleave_roles(keys: list[str]) -> list[str]:
    """Order strata so roles alternate instead of clustering.

    Stratum keys lead with the role, so plain sorting emits every ``author``
    stratum before every ``consumer`` one, and a batch drawn from adjacent
    strata sits wholly inside one role block. Ranking each role's strata by
    relative position mixes the roles evenly. This ordering is only the
    tie-break; ``_interleaved_indices`` spreads each stratum across the whole
    epoch first.
    """
    by_role: dict[str, list[str]] = defaultdict(list)
    for key in keys:
        by_role[key.split("|")[0]].append(key)
    ranked: list[tuple[float, str]] = []
    for role_keys in by_role.values():
        span = len(role_keys)
        ranked.extend(
            ((index + 0.5) / span, key) for index, key in enumerate(role_keys)
        )
    return [key for _, key in sorted(ranked)]


def _shuffled_indices(
    count: int, batch_size: int, rng: np.random.Generator
) -> list[list[int]]:
    """Ordinary shuffling — the baseline for the step-5 comparison."""
    order = list(range(count))
    rng.shuffle(order)
    return _pad_final(_chunk(order, batch_size), batch_size, rng)


def _batch_indices(
    operations: list[str], batch_size: int, rng: np.random.Generator
) -> list[list[int]]:
    """Superseded operation-uniqueness ordering, retained for reproducibility."""
    buckets: dict[str, list[int]] = defaultdict(list)
    for index, operation in enumerate(operations):
        buckets[operation].append(index)
    for indices in buckets.values():
        rng.shuffle(indices)

    batches: list[list[int]] = []
    while any(buckets.values()):
        batch: list[int] = []
        ranked = sorted(
            (operation for operation, indices in buckets.items() if indices),
            key=lambda operation: (-len(buckets[operation]), rng.random()),
        )
        for operation in ranked:
            if len(batch) == batch_size:
                break
            batch.append(buckets[operation].pop())
        while len(batch) < batch_size and any(buckets.values()):
            operation = max(buckets, key=lambda item: len(buckets[item]))
            batch.append(buckets[operation].pop())
        batches.append(batch)

    _pad_final(batches, batch_size, rng)
    rng.shuffle(batches)
    return batches


def build_batches(
    mode: str,
    *,
    strata: list[str],
    operations: list[str],
    batch_size: int,
    rng: np.random.Generator,
) -> list[list[int]]:
    """Dispatch to one of the three orderings."""
    if mode == "interleaved":
        return _interleaved_indices(strata, batch_size, rng)
    if mode == "shuffled":
        return _shuffled_indices(len(strata), batch_size, rng)
    if mode == "operation":
        return _batch_indices(operations, batch_size, rng)
    raise ValueError(f"unknown batching mode {mode!r}")


def stratum_of(row: dict) -> str:
    """The role x capability x prompt-family cell a selection row belongs to.

    Falls back to role x operation for selections predating the curriculum
    repair, which carry no capability.
    """
    role = row.get("cell_role") or row["role"]
    capability = row.get("capability") or row["operation"]
    return f"{role}|{capability}|{row['prompt_family']}"


def batch_diversity(batches: list[list[int]], strata: list[str]) -> dict[str, float]:
    """How many distinct strata a batch spans — the step-5 comparison metric."""
    spans = [len({strata[index] for index in batch}) for batch in batches]
    roles = [len({strata[index].split("|")[0] for index in batch}) for batch in batches]
    families = [
        len({strata[index].split("|")[2] for index in batch}) for batch in batches
    ]
    return {
        "mean_distinct_strata": round(sum(spans) / len(spans), 3),
        "min_distinct_strata": min(spans),
        "batches_with_single_role": sum(1 for value in roles if value == 1),
        "batches_with_single_prompt_family": sum(1 for value in families if value == 1),
    }


def _packed_batch(dataset, indices: list[int], max_seq_length: int):
    batch = [dataset[index] for index in indices]
    if len(batch[0]) == 2:
        token_rows, offsets = zip(*batch, strict=True)
    else:
        token_rows = batch
        offsets = [0] * len(batch)
    lengths = [min(len(row), max_seq_length) for row in token_rows]
    pad_to = 32
    max_length = 1 + pad_to * ((max(lengths) + pad_to - 1) // pad_to)
    max_length = min(max_length, max_seq_length)
    batch_array = np.zeros((len(indices), max_length), np.int32)
    for index, row in enumerate(token_rows):
        batch_array[index, : lengths[index]] = row[: lengths[index]]
    return mx.array(batch_array), mx.array(list(zip(offsets, lengths, strict=True)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--epochs",
        type=int,
        default=1,
        help="Training length in whole epochs; --iters is derived from it.",
    )
    parser.add_argument(
        "--save-every",
        type=int,
        default=19,
        help="Checkpoint interval, so generated evaluation has intermediates.",
    )
    parser.add_argument(
        "--batching",
        choices=BATCHINGS,
        default="interleaved",
        help="Batch ordering; 'shuffled' is the step-5 comparison baseline.",
    )
    parser.add_argument(
        "--model", default="mlx-community/Qwen2.5-Coder-7B-Instruct-8bit"
    )
    parser.add_argument("--num-layers", type=int, default=8)
    parser.add_argument("--rank", type=int, default=8)
    parser.add_argument(
        "--fine-tune-type", default="lora", choices=("lora", "dora", "full")
    )
    parser.add_argument(
        "--max-iters",
        type=int,
        help="Hard cap on updates, for bounded probes. Truncates the epoch.",
    )
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument(
        "--learning-rate",
        type=float,
        help="Defaults to 2e-5 for LoRA and 1e-5 for full fine-tuning.",
    )
    parser.add_argument(
        "--lr-schedule",
        action="store_true",
        help="Linear warmup then cosine decay to a tenth of peak, per the "
        "Mellum 2 report. Off by default so recorded runs stay reproducible.",
    )
    parser.add_argument(
        "--lr-warmup",
        type=int,
        default=100,
        help="Warmup iterations for --lr-schedule; clamped to a quarter of the run.",
    )
    args = parser.parse_args()

    train_rows = [
        json.loads(line)
        for line in (args.data / "train.jsonl").read_text().splitlines()
        if line
    ]
    selection = {
        row["row_id"]: row
        for line in args.selection.read_text().splitlines()
        if line
        for row in (json.loads(line),)
    }
    operations = [selection[row["task_id"]]["operation"] for row in train_rows]
    strata = [stratum_of(selection[row["task_id"]]) for row in train_rows]
    row_ids = [row["task_id"] for row in train_rows]
    # 2e-5 is the LoRA rate every recorded run used. Full fine-tuning updates
    # ~24% of the model rather than 0.076% of it, and 2e-5 is 2-4x the usual
    # full-tune range; leaving it there would make a degenerate result
    # impossible to attribute between "full tuning does not help here" and
    # "the rate was too hot".
    learning_rate = args.learning_rate
    if learning_rate is None:
        learning_rate = 1e-5 if args.fine_tune_type == "full" else 2e-5
    rng = np.random.default_rng(args.seed)
    batch_size = args.batch_size
    batches_per_epoch = -(-len(train_rows) // batch_size)
    iters = batches_per_epoch * args.epochs
    if args.max_iters:
        iters = min(iters, args.max_iters)
    epoch_log: list[list[dict[str, str]]] = []
    diversity: list[dict[str, float]] = []

    def stratified_batches(
        dataset,
        batch_size,
        max_seq_length,
        loop=False,
        seed=None,
        comm_group=None,
    ):
        if len(dataset) != len(operations) or comm_group.size() != 1:
            yield from mlx_iterate_batches(
                dataset=dataset,
                batch_size=batch_size,
                max_seq_length=max_seq_length,
                loop=loop,
                seed=seed,
                comm_group=comm_group,
            )
            return
        epoch = 0
        while True:
            batches = build_batches(
                args.batching,
                strata=strata,
                operations=operations,
                batch_size=batch_size,
                rng=rng,
            )
            diversity.append(batch_diversity(batches, strata))
            epoch_log.extend(
                [
                    {
                        "epoch": str(epoch),
                        "row_id": row_ids[index],
                        "operation": operations[index],
                        "stratum": strata[index],
                    }
                    for index in batch
                ]
                for batch in batches
            )
            for batch in batches:
                yield _packed_batch(dataset, batch, max_seq_length)
            epoch += 1
            if not loop:
                break

    import mlx_lm.lora as lora

    original_train = lora.train
    lora.train = functools.partial(original_train, iterate_batches=stratified_batches)
    sys.argv = [
        "mlx_lm.lora",
        "--model",
        args.model,
        "--fine-tune-type",
        args.fine_tune_type,
        "--train",
        "--data",
        str(args.data),
        "--adapter-path",
        str(args.adapter),
        "--iters",
        str(iters),
        "--batch-size",
        str(batch_size),
        "--num-layers",
        str(args.num_layers),
        "--learning-rate",
        str(learning_rate),
        "--mask-prompt",
        "--max-seq-length",
        "1024",
        "--seed",
        str(args.seed),
        "--steps-per-report",
        "20",
        "--steps-per-eval",
        "80",
        "--save-every",
        str(args.save_every),
    ]
    # mlx_lm exposes no --rank or --lr-schedule flag; both arrive through a
    # config file. Written only when something non-default is requested so the
    # default path stays byte-identical to the runs already recorded.
    sections: list[str] = []
    if args.rank != 8 and args.fine_tune_type != "full":
        sections.append(
            "lora_parameters:\n"
            f"  rank: {args.rank}\n"
            "  dropout: 0.0\n"
            # mlx-lm's scale is a direct output multiplier on the LoRA branch
            # (`y + scale * z`), default 20.0 and independent of rank. Deriving
            # it from rank would have given scale 80 at rank 32, confounding a
            # capacity comparison with a 4x change in adapter output magnitude.
            "  scale: 20.0\n"
        )
    if args.lr_schedule:
        # The Mellum 2 technical report's own SFT warms up linearly over 100
        # iterations to a 3e-5 peak, then cosine decays to 3e-6 -- 10% of peak.
        # Our runs have all used a constant rate, which is the likelier reason
        # a single epoch looked like a ceiling. mlx-lm's `cosine_decay` takes
        # (init, decay_steps, end) and `warmup` prepends a linear ramp.
        #
        # Warmup is clamped: a 100-iteration ramp inside a 30-iteration run
        # would mean the rate never reaches peak at all.
        warmup = min(args.lr_warmup, max(iters // 4, 1))
        # Exponent form must carry a decimal point: YAML 1.1 resolves `3e-05`
        # as a *string*, which reaches mlx-lm's scheduler intact and fails
        # deep inside it with "unsupported operand type(s) for -: 'str' and
        # 'float'". `{:.6e}` always emits a mantissa, so it always parses.
        sections.append(
            "lr_schedule:\n"
            "  name: cosine_decay\n"
            f"  warmup: {warmup}\n"
            "  warmup_init: 0.0\n"
            # Decay over what is left *after* the ramp: mlx-lm offsets the
            # second schedule by `warmup + 1`, so passing the full run length
            # leaves the cosine unfinished and the rate ends at 7.1e-6 rather
            # than the intended 3e-6.
            f"  arguments: [{learning_rate:.6e}, {max(iters - warmup - 1, 1)}, "
            f"{learning_rate / 10:.6e}]\n"
        )
    if sections:
        args.adapter.mkdir(parents=True, exist_ok=True)
        config = args.adapter / "lora-config.yaml"
        config.write_text("".join(sections))
        sys.argv += ["--config", str(config)]
    lora.main()
    args.adapter.mkdir(parents=True, exist_ok=True)
    (args.adapter / "batch-manifest.json").write_text(
        json.dumps(
            {
                "batching": args.batching,
                "batch_diversity": diversity,
                "batch_size": batch_size,
                "batches": epoch_log,
                "batches_per_epoch": batches_per_epoch,
                "epochs": args.epochs,
                "iters": iters,
                "row_count": len(train_rows),
                "save_every": args.save_every,
                "seed": args.seed,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
