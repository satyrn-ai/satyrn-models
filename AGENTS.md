# Repository instructions

Before non-trivial work, read [`DEV_PHILOSOPHY.md`](DEV_PHILOSOPHY.md),
[`specs/design.md`](specs/design.md), the affected contracts, and the nearest
`DEV_NOTES.md` when one exists.

- Follow the knowledge ownership map in [`specs/README.md`](specs/README.md).
  Update the canonical owner and only the entry points or links made stale.
- Proactively surface better options with their trade-offs, even when the
  requested scope does not require them. Push back on suboptimal suggestions
  with technical reasoning.
- Treat the configuration and failure semantics in `DEV_PHILOSOPHY.md` as hard
  constraints.
- The GitHub issue owns work-item knowledge: its body owns scope, requirements,
  acceptance criteria, and dependencies; native issue state and fields own
  status and priority. Treat comments as discussion until an accepted decision
  is incorporated into the body. Keep work-item details out of repository code,
  tests, prompts, specs, DEV_NOTES, and READMEs.
- Keep agent-private storage limited to pointers into canonical repository
  knowledge.

## Additional rules

- Treat repeated bug-preventing guidance as a rule candidate. Propose an
  `AGENTS.md` change before editing it, place it at the narrowest shared scope,
  and keep it concise and testable.
