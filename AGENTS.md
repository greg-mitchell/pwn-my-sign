# Developer & Agent Guidelines

Rules for working in this repo:

1. **Source of Truth**:
   * [README.md](./README.md) for high level setup and human-readable docs.
   * [pyproject.toml](./pyproject.toml) for command definitions (`[tool.poe.tasks]`) and dependencies.
   * [docs/](./docs)
       * [python-style.md](./docs/python-style.md): python style guide (sources)
       * [test-style.md](./docs/test-style.md): style guide for testing in this repo
2. **Pre-commit Checks**: Run `uv run poe check-all` before declaring any task complete or pushing changes. Run commands from the project root. All hooks in [.pre-commit-config.yaml](./.pre-commit-config.yaml) must pass.
   * **Style & Length Constraints**: <120 chars (enforced by `ruff`)
   * **Type Checking**: Strict type annotations are required. Ensure `uv run poe typecheck` (using `ty`) passes.
3. **Commits**: Only after checks pass. Descriptions should use simplified Conventional Commit formatting
   * types are: fix, feat, chore, docs, refactor, test, etc
   * breaking changes must have `!` after the type
   * follow git line length conventions: short description <50 char preferred, body lines wrapped at 72 char
   * use  the imperative mood for the short description
   * explain what and why in the body, not how

```
<type>: short description

body
```

4. **Project boundaries**:
   * [docs/protocol.md](./docs/protocol.md) records observed device behavior. Preserve the verified wire format.
   * [docs/architecture.md](./docs/architecture.md) defines command boundaries and stream contracts.
   * [docs/implementation-plan.md](./docs/implementation-plan.md) distinguishes completed work from WIP.
   * Keep scheduling and workflow state in documented Unix composition. Terminal prompts come first; desktop UI is optional.
   * Keep device identities, Android bug reports, raw Bluetooth captures, and investigation photos in ignored `private/`.
   * Unit tests use injected dependencies and `Mock(spec=...)`; no network, Bluetooth, threads, subprocesses, or patching.
   * Reproduce a bug with a failing test before changing its behavior; report the same test passing afterward.

5. **CLI and workflow conventions**:
   * Use `uv run` with its default implicit synchronization; do not pass `--no-sync`.
   * Install only `mysign` through `[project.scripts]`. Use Click domain groups (`device`, `image`, and future `github`)
     with a focused module for each group or command under `src/greg_mitchell/pwn_my_sign/cli/`.
     Each leaf command remains one composable operation with explicit stream contracts.
   * Keep domain logic outside `cli/`; introduce focused source packages as functionality grows.
   * Keep pure refactors and features in separate commits and organize feature work into separate PRs.
   * Keep user-selected artwork, fonts, personal captions, asset maps, and generated display cards in ignored `private/`.
