from __future__ import annotations

from typing import TYPE_CHECKING

from datasets import Dataset

if TYPE_CHECKING:
    from transformers import PreTrainedTokenizerBase


def pack_documents(
    dataset: Dataset,
    tokenizer: PreTrainedTokenizerBase,
    sequence_length: int,
    max_overlap: float = 0.3,
) -> Dataset:
    """Split long documents into full-length sequences and bin-pack the rest.

    Loosely based on "Improving Continual Pre-training Through Seamless Data Packing",
    https://arxiv.org/abs/2505.22018

    Args:
        dataset: A Dataset with a "text" column.
        tokenizer: Encodes each document and decodes the packed sequences.
        sequence_length: The length no sequence exceeds; bin-packed ones fall short.
        max_overlap: Caps the text repeated to make a document's final window full.

    Returns:
        A Dataset with a "text" column, one row per packed sequence.
    """
    # Leave room for the EOS token the trainer appends to every sequence
    sequence_length -= 1
    max_repeated = int(max_overlap * sequence_length)
    sequences: list[list[int]] = []
    leftovers: list[list[int]] = []

    for text in dataset["text"]:
        tokens = tokenizer(text, add_special_tokens=False).input_ids

        if len(tokens) <= sequence_length:
            leftovers.append(tokens)
            continue

        whole_windows = len(tokens) // sequence_length
        for window_start in range(0, whole_windows * sequence_length, sequence_length):
            sequences.append(tokens[window_start : window_start + sequence_length])

        tail = tokens[whole_windows * sequence_length :]
        if not tail:
            continue

        repeated_tokens = sequence_length - len(tail)
        if repeated_tokens <= max_repeated:
            sequences.append(tokens[-sequence_length:])
        else:
            leftovers.append(tokens[-(len(tail) + max_repeated) :])

    leftovers.sort(key=len, reverse=True)
    bins: list[list[int]] = []
    for fragment in leftovers:
        for packed in bins:
            if len(packed) + 1 + len(fragment) <= sequence_length:
                packed.append(tokenizer.eos_token_id)
                packed.extend(fragment)
                break
        else:
            bins.append(list(fragment))

    sequences += bins
    return Dataset.from_list([{"text": tokenizer.decode(tokens)} for tokens in sequences])
