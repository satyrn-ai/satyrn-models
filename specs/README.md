# Repository Knowledge Map

Use one canonical owner for each concern. Other documents provide navigation
links without restating the same knowledge.

## 1. Canonical owners

| Concern | Canonical owner |
| --- | --- |
| Product intent, desired outcomes, and deliberate non-goals | [`design.md`](design.md) |
| Observable CLI, package, data-format, configuration, and failure behavior | [`contracts/`](contracts/) |
| Package boundaries, data flow, runtime topology, and architectural decisions | [`architecture/project_structure.md`](architecture/project_structure.md) |
| Current shortcomings and their observable impact | [`known_limitations.md`](known_limitations.md) |
| Engineering, configuration, failure, testing, build, and documentation principles | [`DEV_PHILOSOPHY.md`](../DEV_PHILOSOPHY.md) |
| Brand identity, voice, visual tokens, UI components, interaction patterns, and accessibility | [`BRAND_BOOK.html`](../BRAND_BOOK.html) |
| Exact package metadata, entry-point declarations, dependency versions, and configuration values | Nearest `pyproject.toml`, source file, or configuration file |
| Non-obvious implementation rationale and operational pitfalls | Nearest `DEV_NOTES.md`, when one exists |
| Setup, usage, commands, and navigation | Nearest `README.md` |
| Agent operating instructions | Nearest `AGENTS.md` |
| Work-item scope, requirements, acceptance criteria, dependencies, priority, and status | GitHub issue: body for scope and acceptance; native state and fields for status and priority |
| Delivery discussion, implementation diff, review findings, and check results | GitHub pull request |
| Historical experiments, evidence, and discarded directions | Dated artifact under [`spikes/`](../spikes/), indexed by the nearest spike `README.md` |

## 2. Update rule

Update the canonical owner first when behavior, structure, or rationale
changes. Then update only the navigation or entry points made stale.

Keep catalogs of repository knowledge in this map. Other entry points should
link to this map or directly to the one canonical owner they need instead of
enumerating sibling knowledge files.

READMEs may contain tested setup and command examples, but they link to
contracts for complete semantics. Historical artifacts remain snapshots:
current specs may cite them as evidence but never delegate current behavior to
them.
