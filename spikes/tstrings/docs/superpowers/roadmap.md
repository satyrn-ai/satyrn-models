# tstrings-cleanroom roadmap

## Decision

This roadmap sequences the clean-room t-strings spike rebuild described in
`spikes/tstrings/BRIEF.md` into milestones and gates. The BRIEF is the
specification; this document does not repeat its evidence or acceptance
criteria and defers all "why" to it by reference. Its sole job is to tell a
planning model where the plan boundaries are, what each plan's entry and exit
artifacts are, and what must be true before starting the next plan.

## Milestones

| # | Milestone | Phases | Handoff artifact | Entry precondition |
|---|---|---|---|---|
| M1 | Corpus | 0–5 | `corpus-sft/{train,valid}.jsonl` + `manifest.json` | BRIEF committed (done) |
| M2 | Measurement | 6–7 | `REPORT.md` + trained adapters + `PREREGISTRATION.md` | M1 corpus frozen, Phase 5 acceptance green |
| M3 | Upstream | 8–9 | merged PR to `corpus_builder` + Michał-consumable corpus | conversation with Michał (independent of M1/M2) |

M3 is intentionally parallel: it depends on nothing in M1 or M2 and is gated
only on the human conversation with Michał.

## Working method

- **Phases in dependency order.** A phase does not start until the prior
  phase's acceptance passes. This restates the BRIEF's ordering rule.
- **Within a phase, decompose into feature cycles.** A feature cycle is the
  brainstormable unit — it groups one or more of the BRIEF's named
  deliverables into something that warrants its own spec → plan →
  implementation. The decomposition is produced at the start of each phase by
  a Superpowers brainstorm, not pre-listed here.
- **One feature cycle at a time.** The next cycle does not begin until the
  prior is implemented and its acceptance met. No parallel feature cycles
  within a phase.
- **Planning unit.** A plan is written per feature cycle. This roadmap's
  "ready to plan when" gates operate at the phase level; within a phase,
  feature-cycle plans are gated by local brainstorming.

## Roadmap consequences

1. M1 starts from the BRIEF; nothing precedes it.
2. M1 is ready to plan when the BRIEF is committed (it is). Within M1, each
   phase gets its own brainstorm producing serial feature-cycle specs and
   plans.
3. If a planning model cannot hold Phases 0–5 in one effort, split at
   Phase 2/3. The sub-split's handoff is `tasks/built.jsonl` (unverified
   candidate tasks); M1's frozen deliverable remains `corpus-sft/` regardless
   of whether the split is taken.
4. M2 is ready to plan when M1's Phase 5 acceptance passes — the corpus is
   frozen, contamination check green, lineage split clean. M2 may not be
   planned against a provisional corpus.
5. M2 is not itself splittable at 6/7 — the Phase 7 preregistration must name
   the exact metric the Phase 6 harness validates. If a split is forced there,
   freeze the validated metric to a file at the end of Phase 6 and have
   Phase 7 reference it verbatim.
6. M3 may be planned and executed at any time; it is gated on a conversation,
   not on M1 or M2.
7. The whole effort is complete when M2 lands a `REPORT.md` reporting mean
   and spread per arm against the preregistered decision rule, with at least
   five adapters. M3 is not on the critical path.
8. **M4 (optional corpus expansion)** — Phase 10 re-opens M1's sourcing to
   admit the pinned third-party repositories (regex-template, t-sql, tdom,
   storyville, tdom-svcs, pep750-examples) and re-runs the corpus pipeline
   over the larger seed pool. Independent of M2/M3; it enriches the handoff
   corpus and Michał-format dataset.

## Completion

The rebuild is complete when M2's `REPORT.md` states whether the
preregistered decision rule was met — or reports a negative result plainly —
with at least five adapters. M3 is a separate, independently schedulable
contribution.
