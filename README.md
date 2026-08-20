# Satyrn Models

This repo's primary purpose is to serve as a pipeline for fine-tuning models for Satyrn AI. The repo provides:

- tools for producing datasets used for fine-tuning
- workflows for training and evaluating models

This repo will capture knowledge about the Python language and standard library
that were introduced after a base model's knowledge cutoff date.

## Repository knowledge

The [knowledge ownership map](specs/README.md) is the single index for current
specifications, contracts, engineering guidance, and historical evidence.

Read the [product design](specs/design.md) for intended outcomes, the
distinction between current and planned capabilities, and deliberate
boundaries.

## Packages

- [Corpus builder](corpus_builder/README.md)
- [Unsloth trainer](trainer/unsloth/README.md)
