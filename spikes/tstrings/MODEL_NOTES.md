# Notes on Mellum2 as the target model

For anyone extending this spike to another checkpoint or writing more
authoring docs. Source: `MELLUM_ISSUES.md` and `MELLUM2_REFERENCE.md` from the
2026-08 investigation (arXiv:2605.31268), condensed to what survived.

- **mlx-lm needs the git-main branch, not the PyPI release.** `mellum`
  support is git-main-only; the newest PyPI release (0.31.3) raises `Model
  type mellum not supported`. Pin to a commit, not a range — an unpinned
  resolve to PyPI silently breaks the ability to load the target model at
  all.
- **Build on Instruct, not Thinking.** The Mellum 2 technical report's own
  published protocol (0.0 temperature, greedy decoding, pass@1) matches this
  project's harness — informal team guidance suggesting otherwise describes
  their eval backlog, not what the report ran. Instruct's perfect termination
  and 3.6x shorter outputs make it the variant to build on.
- **The low score is real, not a wrong-regime artifact.** This project's task
  shape (function-level synthesis) sits in Mellum's strongest coding regime
  (EvalPlus 78.4, leading its comparison panel). The knowledge gap for a
  post-cutoff language feature like PEP 750 sits on the report's own confirmed
  weakest axis (world knowledge, MMLU-Redux 78.1 vs. a 91.1 comparator). A poor
  score cannot be explained away as testing the wrong ability.
- **The base model's specific wrong prior:** it confabulates an earlier,
  rejected PEP 750 draft — a "tagged template literal" with `.tag`, `.parts`,
  `.values`, and a `str` subclass — instead of the accepted
  `string.templatelib.Template` with `.strings`, `.values`, `.interpolations`.
  In code generation it sometimes reads "t-string" as "triple-quoted string."
  Worth knowing when authoring more tasks or documentation-in-prompt content.
- **Delivery format:** the report's SFT schema is `messages` plus optional
  `tools` and `reasoning`; this project's data belongs in their *single-turn
  coding* category, which is why `corpus-sft/` is shaped that way.
