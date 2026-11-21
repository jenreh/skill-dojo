# AGENTS.md

---

## 1) Golden Rules

**NEVER** guess — **ALWAYS** read the doc first (use Context7 or a skill)!

1. **Think → Memory → Tools → Code → Memory.** Use code-reasoning; search Memory and claude-context first; minimal diff; write learnings back.
2. **Tests are truth.** Failures → fix code first. Change tests only if clearly wrong spec.
3. **Minimal diff.** Add tests before code. Keep simple.
4. **Consistency > cleverness.** Follow SOPs and stack idioms.
5. **Memory multiplies.** Persist decisions, patterns, error signatures, proven fixes.
6. **Files ≤ 1000 lines.** Exceed → refactor (see §5).
7. No extensive docs/summaries/comments unless requested.
8. No `cat` to create files; use tools.
9. Log default: `logger.debug`. Important events: `logger.info`. Issues only: `logger.warning/error`. **No `print`.**
10. **Caveman skill** applies to all writes here.

> Prefer *local* changes over cross-module refactors.

---

## 2) Task Bootstrap Pattern

```markdown
<!-- plan:start
goal: <one line clear goal>
constraints:
- Python 3.14; Typer CLI; Reflex web UI; Pydantic 2.14; ruamel.yaml;
- logging: no f-strings in logger calls
- files ≤ 1000 lines; apply design patterns where appropriate
- minimal diff; add/adjust tests first
- three uv workspace packages (core, CLI, web); all logic in core
definition_of_done:
- tests pass; coverage ≥ 80%; lint/type checks clean; memory updated
steps:
1) Search Memory for "<keywords>"
2) Draft/adjust failing test to capture expected behavior
3) Implement minimal code change
4) Run task test; iterate until green
5) Update Memory: decisions, patterns, error→fix
plan:end -->
```

---

## 3) Tooling Decision Matrix

| Situation | Primary | Secondary | Store to Memory |
| --- | --- | --- | --- |
| API/pattern uncertainty | **Context7** | — | Canonical snippet + link; edge cases |
| Ecosystem bug/issue | **DuckDuckGo** | Context7 | Minimal repro; versions; workaround |
| Repeated test failure | **Memory (search)** | Context7 | Error signature → fix; root cause |
| New feature scaffold | **Context7** | — | How‑to snippet; checklist |
| House style/tooling | **This file** | Context7 | Checklist results |

Prefer official docs; widen via web search for cross-version issues.

---

## 4) SOP — Development Workflow

**Task Runner:** `task` (via `Taskfile.dist.yml`), not `make`.

### Prepare

1. Memory first — search prior solutions.
2. Reasoning plan — Task Bootstrap Pattern.
3. `task test` — snapshot current failures.

### Triage Failures

- Read first failing assertion; map to spec.
- Tests match spec → fix code. Diverge → document; adjust spec/tests (after approval).
- Add/adjust unit tests to codify expected behavior.

### Implement (Minimal Diff)

- Tests-first for new behavior. Approved stacks only. Apply design patterns (see §5).
- **No `print`.** Use `logging` module.
- **No f-strings in logger calls:**

  ```python
  import logging

  log = logging.getLogger(__name__)
  log.info("Loaded items: %d", count)  # ✅
  # log.info(f"Loaded items: {count}") # ❌
  ```

### Quality Gates

- `task lint` (format + typecheck), `task format`, `task typecheck` (ty only), `task audit` (uv audit).
- `task upgrade` upgrades all dependencies to their latest allowed versions.
- `task test` — coverage ≥ **80%**.

### Commit & PR

- Conventional Commits (`feat:`, `fix:`, `refactor:`…).
- PR: description, `Closes #123`, screenshots, migration rationale.

### Learn → write to **Memory**

### Dependencies

- Add dependencies always via `uv add <library name>`

---

## 5) Python Code & Testing

Full rules in **python-coding** skill. Key:

- Python 3.14; uv; line length **88**.
- No f-strings in logger calls.
- Files ≤ 1000 lines.
- Coverage ≥ 80%.
- Type annotations on all functions/methods.
- **Architecture**: three uv workspace packages, flat modules inside (see §6).

---

## 6) Architecture: uv workspace packages

```
components/
├── skill-dojo-core/   # dist skill-dojo-core, module skill_dojo_core: all behaviour
├── skill-dojo-cli/    # dist skill-dojo (console script skill-dojo), module skill_dojo_cli
└── skill-dojo-web/    # dist skill-dojo-web, module skill_dojo_web (Reflex UI, [web] extra)
tests/e2e/             # cross-package tests; tests/support has the shared fakes
```

Key rules:

- The boundary is between packages, not layers. No ports/adapters, no composition root.
  Plain modules by concern, plain functions; classes only where state is needed.
- `skill_dojo_core` imports neither `typer`, `reflex`, nor the other two packages
  (a test enforces this). CLI and web contain no business logic and import only from
  `skill_dojo_core` (its `__init__` is the public API).
- Every `skill_dojo_core.commands` function takes a `Context` (repo, github, actor, now,
  progress). Core never reads cwd, env vars or `gh auth`, never prints or prompts.
  Results are pydantic models; failures are typed errors from `skill_dojo_core.errors`.
- Writes take the per-repo lock (`repo_lock`, `registry/.lock`).
- The only test seam is the `GitHub` Protocol (fake in `tests/support`). Git and the
  filesystem are always real (bare repos under `tmp_path`).
- `skill-dojo serve` imports `skill_dojo_web` lazily; core + CLI release without web.

---

## 7) Security & Config

- No credentials in code/history; `gh auth` locally, GitHub Actions secrets in CI.
- No default accounts or passwords, also not in migrations. Bind published ports to `127.0.0.1` unless a deployment needs more.
- Parameterized logs; no sensitive values.
- `git`/`gh` run with argument lists, never a shell. GitHub event data reaches `run:` scripts through `env:` only.
- Pin everything that executes: actions by SHA, images by version, hooks by frozen SHA.
- Update vulnerable deps; document CVE-driven updates in commits & Memory.
- The web UI is local only and binds to `127.0.0.1`.

See `SECURITY.md` for the deployment checklist.

---

## 8) Search SOPs

- **Context7 first** for framework truths; cite in Memory.
- **DuckDuckGo** for cross-version issues; prefer official docs.
- Store only final answer: minimal snippet + rationale + version pins + link.

---

## 9) Task Checklist / Definition of Done

use **code-review** skill and ensure:

- [ ] Tests added/updated; all green
- [ ] Coverage ≥ 80%
- [ ] task lint` pass
- [ ] No file > 1000 lines
- [ ] Clean architecture, no code smells, used **python-clean-code** principles
- [ ] Migrations reviewed & documented
- [ ] Documentation & README.md updated
- [ ] Memory updated (decisions, patterns, error→fix, learnings)

---

## 10) Important Skills

Project-specific skills live in `.agents/skills/` (`.claude/skills` links to it).
General skills come from the plugin marketplaces in `.claude/settings.json`
(`task agents:plugins` installs them):

- **jenreh/agent-skills**: the `jenreh-*` plugins listed below.

Only the jenreh skills matching this project's configuration are listed below.

| Skill | Purpose |
| --- | --- |
| `python-coding` | Python 3.14 style, logging, type annotations, design patterns, testing |
| `python-clean-code` | Enforce Clean Code Developer (CCD) architecture and software quality principles |
| `code-cleanup` | Refactor and simplify Python files modified in the current session if they get complex/big |
| `boost` | Use when the user wants to refine, sharpen, or expand a rough idea into a detailed implementation prompt |
| `reflex-state-and-architecture` | State design, event handlers, background tasks, form validation, page factory, service registry, repo pattern, DB models, architecture |
| `reflex-testing-state` | Pytest unit tests for Reflex State — event handlers, computed vars, substates |
| `reflex-docs` | Reflex.dev framework documentation |
| `frontend-design` | Create distinctive, production-grade frontend interfaces |
| `ui-ux-pro-max` | UI/UX design intelligence — styles, palettes, font pairings, UX and accessibility guidelines, charts |
| `design-system` | Design token architecture (primitive → semantic → component), CSS variables, component specs |
| `appkit-mantine-reference` | Full API for appkit_mantine components — inputs, layout, overlays, charts, data display, navigation |
| `appkit-commons` | app configuration, service registry, DB repository pattern, DB entities, DB custom column types, scheduler |
