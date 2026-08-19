# Development Philosophy

This repo is maintained by a small team. The goal is to keep the codebase
**simple, explicit, and predictable** for humans and AI agents.

## How to use this document

- Before **non-trivial** work (new feature, refactor, configuration or contract
  change), skim this document and the nearest relevant `DEV_NOTES.md` when one
  exists.
- Keep **one canonical place** for each contract or piece of knowledge. Other
  documents link to it instead of duplicating it.

## Clean Code (readability first)

Code should be easy to read, understand, and modify.

- **Meaningful names**: variables, functions, and types should reveal intent.
- **Small units**: one function, module, or class has one responsibility. If
  its description needs “and,” consider splitting it.
- **DRY (Don’t Repeat Yourself)**: remove meaningful duplication because it is
  a drift and bug source.
- **Comments explain “why,” not “what”**: use comments and docstrings for
  non-obvious intent or trade-offs, not code mechanics.
- **Single level of abstraction**: do not mix high-level orchestration with
  low-level details in the same unit.
- **No magic numbers**: give domain-significant values meaningful names; make
  them validated inputs with explicit defaults when they are configurable.
- **Long-term clarity over short-term speed**: use explicit contracts and
  predictable behavior.
- **Simplest sufficient design**: avoid speculative abstractions.
- **Boy Scout Rule**: leave touched code clearer than you found it.

## Responsibility boundaries (Clean Architecture, pragmatic)

Each component does its job without absorbing foreign responsibilities.

- **Composition root composes**: wiring happens at the application or bootstrap
  edge. Core logic does not own framework or runtime wiring.
- **Dependency direction**: dependencies point inward. Outer layers may depend
  on inner layers, not the reverse.
- **No framework leakage into core**: business and service logic does not
  depend on web frameworks or UI toolkits.
- **Put behavior with its owner**: do not place domain logic in settings or an
  application factory merely because the caller is nearby.
- **Respect the product contract**: override framework defaults when they
  conflict with required behavior or UX.

## SOLID and Domain-Driven Design (pragmatic constraints)

Use these ideas to protect clarity and boundaries, not as goals by themselves.

- **Single Responsibility**: keep units focused on one reason to change.
- **Open/Closed**: extend behavior behind stable contracts when practical.
- **Liskov Substitution**: implementations of one contract preserve behavior
  and failure semantics.
- **Interface Segregation**: keep interfaces and configuration objects narrow.
- **Dependency Inversion**: depend on contracts; bind implementations at the
  composition root.
- **Bounded contexts**: integrate through explicit public APIs and contracts,
  never consumer imports of implementation internals.
- **Ubiquitous language**: use the same product vocabulary in code, tests, and
  documentation.

## Configuration as a contract

- **One key = one semantic concept**: do not overload configuration values with
  sentinel meanings.
- If there is a **mode + a value**, model them as separate inputs.
- **Validate and normalize once at the boundary**. Downstream code consumes the
  canonical value and does not reinterpret configuration.
- **Fail fast** on missing, malformed, or contradictory inputs.
- **Fallbacks are prohibited**: do not change the requested capability, model,
  or output contract after a failure. Redundant infrastructure may retry the
  same contracted behavior. An explicit, validated default is allowed when it
  is a normal value in the contract.
- Existing violations are recorded in
  [`specs/known_limitations.md`](specs/known_limitations.md). Documenting an
  exception does not make it an approved pattern for new work.

## Documentation and knowledge (avoid drift)

- Treat documentation and specifications as **living knowledge**.
- Keep each concern in one canonical owner and link to it from other entry
  points.
- Keep links and claims aligned with current behavior; remove stale guidance
  quickly.
- Write mandatory guidance as direct affirmative instructions. Use words such
  as "may" or "optional" only when the choice is genuinely optional.
- Write scope affirmatively. An explicit non-goal is the exception: keep one
  only when it protects an important boundary or deliberate product decision.

## Build and packaging

- Treat Docker build context as part of the shipped build contract; manage
  `.dockerignore`, install inputs, and build steps intentionally.

## Testing as executable specification (pragmatic)

- Tests validate **behavior and contracts**, not implementation details.
- Use TDD when it reduces risk, not as dogma.
- Use property-based testing only for high-leverage pure invariants such as
  parsers, normalizers, and validators.
