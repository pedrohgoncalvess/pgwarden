# AGENTS.md — Python Project Conventions

## Programming paradigm
- Default to functions. Logic should live in plain functions and modules, not classes.
- Classes are allowed only for:
  - Stateful service interfaces holding a connection or session (e.g. `DatabaseConnection`, API clients, cache clients, message queue clients). The state (connection, socket, session) is the reason a class is justified here — not convenience.
  - Established patterns that require them (e.g. ORM models, Pydantic schemas, Django models).
  - Data containers with no behavior, via `@dataclass` or `NamedTuple` — used to pass structured data between functions, not to hold logic.
  - Custom exceptions (must subclass `Exception` or a relevant built-in).
  - Framework-mandated base classes (e.g. test case classes, abstract base classes required by a plugin system).
- If a task seems to call for a new class outside those cases, ask the user first with a short justification instead of writing it.
- Do not build inheritance hierarchies unless a framework requires it (e.g. Django models). Composition over inheritance.

## File size
- Source files must not exceed 200 lines. This limit does not apply to test files.
- If a source file would need to exceed 200 lines, split the logic into smaller modules first. Only exceed the limit if splitting is genuinely impractical, and say why when you do.

## Comments
- No section-divider comments (e.g. `# ----- DATABASE CONNECTION`). If you feel the need for one, split that section into its own function or module instead.
- No inline trailing comments (e.g. `people_age = people.age  # this line gets the age`). If a line needs explaining, the code is unclear — rename or restructure it instead.
- Comments are only for explaining **why**, never **how** or **what**. Use them for non-obvious tradeoffs, constraints, or decisions that the code itself can't express (e.g. `# retried here because upstream API is flaky under load`).
- Docstrings are required for all public functions and classes, and must follow PEP 257.

## Naming
- Function names must be short and state their intention directly, verb-first (e.g. `get_active_users`, not `process` or `handle_data`).
- Avoid abbreviations unless they are domain-standard within this project.

## Tests
- Never modify an existing test on your own judgment. If a test appears to need changing, stop and ask the user first, including:
  - Which test and what specifically would change.
  - Why the current test no longer reflects correct behavior.
  - What change in the code motivated this.
- Wait for explicit confirmation before editing the test.

## Formatting & typing
- Follow PEP 8.
- Type hints are required on all function signatures (params and return type).
- Keep functions small and single-purpose. If a function is doing more than one thing, extract a helper function rather than growing it.

## When in doubt
- If a change doesn't clearly fit a rule above, ask before proceeding rather than guessing.
- If you identify a recurring pattern worth codifying (e.g. error handling, logging, import ordering), propose an addition to this file rather than applying it silently.