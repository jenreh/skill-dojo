# skill-dojo: multi-phase implementation plan

Basis: `spec/2026-11-21-curated-marketplace-design.md` (approved design). After approval,
this plan is also saved as `spec/2026-11-21-curated-marketplace-plan.md`.

## Context

Skills from other marketplaces are copied into the jenreh plugins by hand, and the copies
go stale unnoticed. The design turns any GitHub repo into a curated marketplace where every
item (mirror, bundle, local, MCP server) is pinned to an exact commit, hashed, and only
changes through a reviewed candidate PR into `staging`, then a promote PR into `main` and a
dated tag. The tool is a CLI plus an optional local web UI. The first user is
`jenreh/agent-skills` (local clone: `/Users/jens/Workspace/templates/agent-skills`).

## Decisions taken for this plan

- **CLI name is `skill-dojo`** (user, overrides `skit` in the spec). The CLI is the PyPI
  distribution `skill-dojo` with the console script `skill-dojo`. In CI:
  `uvx skill-dojo==X.Y.Z <command>` (no `--from` needed). Phase 0 updates the spec text
  (`skit` → `skill-dojo`; repo path is `/Users/jens/Workspace/projekte/skill-dojo`).
- **Three uv workspace packages** (user): core, CLI, web UI. See Architecture.
- **Adopt the jenreh repo early** (phase 2), right after validate/build/local exist (user).
- **One PR per phase into `skill-dojo` main; first PyPI release at the end** (user).
  Until then the curated repo pins the tool by commit, both packages at the same SHA:
  `uvx --with "git+https://github.com/jenreh/skill-dojo@<sha>#subdirectory=components/skill-dojo-core" --from "git+https://github.com/jenreh/skill-dojo@<sha>#subdirectory=components/skill-dojo-cli" skill-dojo <cmd>`,
  recorded in `registry/config.yaml` as `tool: {git: <40-char-sha>}` (the generated
  workflows build that command from it). Phase 7 switches to `tool: {version: X.Y.Z}`.
  Both are exact pins, so the "pin everything" rule holds.
- **Fetching upstream: the `git` CLI** (partial clone `--filter=blob:none`, checkout of the
  pinned commit, sparse to the item path). It works the same against GitHub and against the
  local bare fixture repos the end-to-end tests need (no network).
- **GitHub access: the `gh` CLI** in core's `github.py` (`gh pr create`, `gh api` for reviews,
  `gh pr merge`). Locally it uses `gh auth`; in Actions `GH_TOKEN`. Tests use a fake
  `GitHub` that records PRs and merges with local git.
- **YAML: `ruamel.yaml`** (round-trip) for `registry/*.yaml` and `SKILL.md` frontmatter, so
  hand edits and comments survive and upstream frontmatter is merged, never rewritten.
- **Hashes.** `lock.json` stores per file `sha256` of the upstream bytes, and for files the
  tool stamps (`SKILL.md`, `plugin.json`) also `normalizedSha256`: the hash after removing
  the tool's namespaced keys and canonicalizing (frontmatter map → canonical JSON + body
  bytes; JSON → sorted canonical JSON). The "archive SHA-256" is `treeSha256` = sha256 of the
  sorted lines `<mode> <sha256> <path>\n` over all item files. Drift = any mismatch.
- **All unpinned MCP servers in jenreh-core get pinned**, not only context7:
  `@upstash/context7-mcp`, `@mettamatt/code-reasoning` (npx) and `duckduckgo-mcp-server`
  (uvx). Otherwise `validate` fails on them.
- `vendor` (replaces `add-skills.sh`) moves into phase 2, because adoption deletes `scripts/`.

## Architecture: three uv workspace packages, flat modules inside

The clean boundary is between packages, not between layers inside them. skill-dojo reads
and writes files, runs `git` and `gh`, and makes a few HTTP calls; it has no swappable
backends, so there are no ports/adapters or composition root. Each package is plain
modules by concern and plain functions. The layout follows the existing `components/`
pattern of `jenreh/appkit` (`components/<dist>/src/<module>/`), which the skill-dojo
template already prepares (`components/.gitkeep`, `uv sync --all-packages` in CI).

```
skill-dojo/                              # workspace root, virtual (not published)
├── pyproject.toml                       # [tool.uv.workspace] members = ["components/*"]
│                                        #   [tool.uv] package = false, shared dev group,
│                                        #   ruff/ty/pytest/coverage config for all
├── components/
│   ├── skill-dojo-core/                 # dist "skill-dojo-core", module skill_dojo_core
│   │   ├── pyproject.toml               # deps: pydantic, ruamel.yaml, httpx
│   │   ├── src/skill_dojo_core/
│   │   │   ├── models.py     # pydantic models for registry/*.yaml and lock.json
│   │   │   ├── registry.py   # load/save registry files (ruamel round-trip)
│   │   │   ├── hashing.py    # file/tree hashes, normalization, drift check
│   │   │   ├── metadata.py   # stamp SKILL.md metadata and plugin.json extensions.<ns>
│   │   │   ├── validate/     # plugins.py, skills.py, registry.py (ports of jenreh scripts)
│   │   │   ├── build.py      # catalogs, missing manifests, branding, layout symlinks
│   │   │   ├── sources.py    # upstream catalogs: agent_plugins, claude, git, mcp_registry
│   │   │   ├── git.py        # thin git CLI wrappers (ls-remote, fetch, branch, commit)
│   │   │   ├── github.py     # GitHub Protocol + gh implementation (the only fake seam)
│   │   │   ├── risk.py       # risk flags from a tree diff
│   │   │   └── commands/     # the operations: init, items (local/mirror/bundle/sync),
│   │   │                     #   review, release (promote/release/revoke), clients, vendor
│   │   └── tests/
│   ├── skill-dojo-cli/                  # dist "skill-dojo", module skill_dojo_cli
│   │   ├── pyproject.toml               # deps: skill-dojo-core, typer
│   │   │                                #   extra [web]: skill-dojo-web
│   │   │                                #   script: skill-dojo = "skill_dojo_cli.main:app"
│   │   ├── src/skill_dojo_cli/          # main.py + one module per command group
│   │   └── tests/
│   └── skill-dojo-web/                  # dist "skill-dojo-web", module skill_dojo_web
│       ├── pyproject.toml               # deps: skill-dojo-core, reflex, appkit-mantine
│       ├── src/skill_dojo_web/          # Reflex app, pages, states
│       └── tests/
└── tests/e2e/                           # cross-package end-to-end tests, fixture repos
```

Dependency rules (one direction only):
- `skill-dojo-core` imports neither `typer` nor `reflex` nor the other two packages. All
  behaviour lives here; `commands/*` is its public API.
- `skill-dojo` (CLI) and `skill-dojo-web` depend only on core and contain no business
  logic: they parse input, call `skill_dojo_core.commands`, and present the result.
- `skill-dojo serve` imports `skill_dojo_web` lazily; without the `[web]` extra it prints
  the install hint (`uv tool install "skill-dojo[web]"`). The web package never imports
  the CLI.
- A small test in core asserts the rule (no `typer`/`reflex`/`skill_dojo_cli`/
  `skill_dojo_web` import under `src/skill_dojo_core`).
- Workspace wiring: root `[tool.uv.sources]` marks the three as `{ workspace = true }`.
  All three share one version line, bumped together by bump-my-version.

### Release without the web UI

- The CLI's `[web]` extra uses a compatible-release pin (`skill-dojo-web~=X.Y.0`), so a
  core + CLI release does not require a web release of the same patch version.
- `task release:publish` publishes `skill-dojo-core` and `skill-dojo` by default and
  `skill-dojo-web` only with `-- --web` (`uv build --package <dist>` per package). The
  PyPI workflow has the same switch. CI checks that the CLI wheel installs and runs
  `validate` in a venv without the web package.

### CLI today, server later (no big refactoring)

Core is written as if its caller were a server, so a later `skill-dojo-server` package
(an HTTP API and/or a multi-user web UI) only adds a front end, auth and a workspace
manager, and calls the same functions. Rules for every `skill_dojo_core.commands`
function:
- **Explicit context, no globals.** Each operation takes a `Context` (frozen dataclass:
  `repo: Path`, `github: GitHub`, `actor: str`, `now: datetime`,
  `progress: Callable[[str], None] | None`). No reads of `cwd`, environment variables or
  `gh auth` inside core; the CLI builds the `Context` from cwd and `gh`, a server would
  build it per request from the user's token and a checked-out workspace.
- **Data in, data out.** Inputs are plain arguments or pydantic models; results are
  pydantic models (JSON-serializable, so a server can return them unchanged). No
  printing, no prompts, no `typer`/`sys.exit` in core; failures are typed exceptions
  from `skill_dojo_core.errors` that the CLI maps to exit codes and a server would map to
  HTTP status codes.
- **No interactive confirmation in core.** Choices (versions to pin, approve/reject) are
  arguments. Confirmation prompts live in the CLI or UI.
- **Safe for concurrent callers on one repo.** Operations that write take a per-repo file
  lock (`registry/.lock`, gitignored) so two UI sessions or a future server worker cannot
  interleave writes.
- **Stable public API.** `skill_dojo_core/__init__.py` exports the command functions,
  `Context`, result models and errors; CLI and web import only from there. A test checks
  every command result round-trips through `model_dump_json()`.
- The current local web UI already follows this path: Reflex's backend is a server that
  calls core in-process. Moving to a hosted version later means adding login and
  per-user tokens around the same calls, not rewriting the logic.

Rules inside a package:
- Pure logic (hashing, normalization, risk flags, policy checks, version bumps, metadata
  mapping) is plain functions taking data and returning data, unit-tested without I/O.
  No classes where a function will do.
- One test seam: core's `GitHub` Protocol with the real `gh` implementation and an
  in-memory fake (shipped in core's tests, reused by CLI/web/e2e tests via a pytest
  plugin fixture in the root `conftest.py`). Git and the filesystem are always real (local
  bare repos under `tmp_path`); the MCP Registry is a real HTTP fake via
  `pytest-httpserver`. No other abstractions until a second implementation exists.
- Split a module into a sub-package only when it nears 1000 lines.
- Phase 0 replaces the hexagonal text in CLAUDE.md §2/§5/§6 with this layout and rules.

General rules: no `print` (CLI output via `typer.echo` in the CLI package only;
everything else `logging`, no f-strings in logger calls), type hints everywhere, files
≤ 1000 lines, coverage ≥ 80 % per package, `task lint` (ruff + ty) clean, Conventional
Commits. Every phase starts with failing tests (TDD, `test-driven-development` skill).

Test layout: `components/<pkg>/tests/test_<module>.py` per package; `tests/e2e/` at the
root with a `fixture_repos` pytest factory that builds bare git repos (an Agent Plugins
marketplace, a Claude marketplace, a plain git repo, a curated repo) under `tmp_path`.

---

## Phase 0: Scaffold cleanup and CLI skeleton

Goal: the uv workspace with three installable packages, no database, a `skill-dojo` CLI
skeleton and the test harness.

1. Remove the DB and login parts of kit-template (call 1a): `alembic/`, `alembic.ini`,
   `app/bootstrap_admin.py`, `app/pages/users.py`, `app/roles.py`, `taskfiles/Taskfile.db.yml`
   (and its include), email templates, DB/OAuth config keys and CI env secrets in
   `.github/workflows/01_ci.yml`, devcontainer Postgres service. Drop `appkit-user`,
   `psycopg`, `sqlalchemy`, `alembic`.
2. Turn the root into a virtual uv workspace (`members = ["components/*"]`,
   `package = false`) and create the three packages with `uv init --package --lib`
   under `components/`. Add dependencies with `uv add --package <dist> ...`
   (core: `pydantic`, `ruamel.yaml`, `httpx`; CLI: `skill-dojo-core`, `typer`, optional
   `web = ["skill-dojo-web"]`; web: `skill-dojo-core`, `reflex`, `appkit-mantine`).
3. Move the Reflex scaffold from `app/` into `components/skill-dojo-web/src/skill_dojo_web/`
   and point `rxconfig.py` at it. Delete `app/`.
4. Root config: ruff `known-first-party` for the three modules, ty `src` roots, pytest
   `testpaths` (`components/*/tests`, `tests`), coverage `source` for the three modules,
   bump-my-version entries for all three `pyproject.toml` files. Update Taskfile `PROJECT`
   var (it parses hatch `packages` today) and `reflex` tasks. Drop the JS test job in CI
   if no `components/*/tests/js` exists.
5. CLI: `skill-dojo --version` and an empty command tree with `--help` text for every
   command group from the spec's CLI sketch (stubs exit with "not implemented");
   `-v/--verbose` → DEBUG logging.
6. Core API skeleton: `Context`, `errors.py`, the public `__init__` exports, the per-repo
   file lock, and the CLI helper that builds a `Context` from cwd + `gh`.
7. Test harness: the fake `GitHub` and the `fixture_repos` factory, shared through the
   root `conftest.py`. Time comes in through `Context.now`, so no clock abstraction. The
   core dependency-rule test and the result round-trip test.
8. Update the spec text (`skit` → `skill-dojo`, three packages), CLAUDE.md (§2/§5/§6:
   workspace layout and the core API rules instead of hexagonal), README stub.

Done: `uv sync --all-packages` works; `uv run skill-dojo --help` works; installing only
`components/skill-dojo-cli` into a fresh venv pulls no Reflex; `uv build --all-packages`
builds three wheels; `task lint` and `task test` green; CI green without DB secrets.

## Phase 1: Registry files, build, validate, local items, init

Goal: the core that reads and writes a curated repo, with no network.

1. **Schemas** (pydantic models + ruamel store) for `registry/config.yaml` (namespace,
   tool pin, layout options, branding, categories), `sources.yaml`, `items.yaml`
   (`id`, `kind`, `source`, `upstreamPlugin`/`parts`, `ref`, `commit`, `quarantined`,
   `supportedChannels`, `riskTier`, `dataClassification`), `approvals.yaml`,
   `channel-policy.yaml` (default riskTier/classification, reviewers per tier, channel
   rules), `clients.yaml`, `lock.json` (per item: kind, upstream repo/commit/path,
   `treeSha256`, files with `sha256`/`normalizedSha256`). Namespace default derived from
   the marketplace name (`<name>.registry/`, `com.<name>.registry`).
2. **Provenance stamping** (`metadata.py`): merge the field set into `SKILL.md`
   `metadata` (flat, string-only, prefixed keys; lists comma-joined; `deprecation` as two
   keys) and into `plugin.json` `extensions.<ns>`. Never touch other keys or extensions.
3. **Hashing and drift** as decided above.
4. **Validation module**, ported from `scripts/validate_plugins.py` (Agent Plugins 1.0
   manifest + MCP schema, symlink containment, marketplace checks, `com.openai` interface)
   and `scripts/validate_skills.py` (frontmatter, `agents/openai.yaml`, flat view). Keep the
   error/warning split. Add: untracked folder under `plugins/` = error; lock ↔ in-file
   metadata disagreement = error; drift = error; floating MCP reference (`latest`, no
   version, unpinned `npx -y pkg`, `uvx pkg`, image without digest) = error;
   metadata values not strings or not namespaced = error.
   *Changed in phase 2 (adoption of jenreh/agent-skills):* only values in the tool's
   own namespace must be strings (error). Non-string or non-namespaced keys outside
   it are warnings for every item, because vendored upstream skills use them
   (`author`, `version`, nested `openclaw` blocks) and cannot be edited without
   forking. Adoption reports such skills as possibly vendored; phase 3 turns them
   into mirror or bundle parts.
5. **`build`**, ported from `scripts/codex_metadata.py` and `scripts/link-plugins.sh`:
   both catalogs (`.agents/plugins/marketplace.json`, `.claude-plugin/marketplace.json`)
   from `plugins/` + `registry/`, missing per-plugin manifests, optional branding
   (`extensions.com.openai.interface`, `agents/openai.yaml` stubs), layout options
   (manifest symlinks, `mcp.json` symlink, flat `skills/<name>` view). The hardcoded plugin
   list/descriptions/keywords in `link-plugins.sh` become data from `items.yaml` and the
   manifests. `build` is idempotent.
6. **`local add <plugin-dir>`**: register a local plugin, write its lock entry
   (`upstreamCommit` = repo HEAD) and stamp metadata. **`lock refresh [--item]`**:
   recompute a local item's lock entry after an edit (used in phase 3 candidate PRs).
7. **`init`**: scaffold `registry/`, empty catalogs, and `.github/workflows/
   validate-marketplace.yml` (actions pinned by SHA, tool pinned per `config.yaml`, runs
   `skill-dojo validate` and `build --check`). `build --check` fails when `build` would
   change files.

Done: unit tests per core module; e2e: `init` a fixture repo, `local add`,
`build`, `validate` pass; hand-edit `registry/` + a catalog → `build && validate`
consistent; change a stamped file by hand → drift; stamping alone → no drift.

## Phase 2: Adopt jenreh/agent-skills, plus `vendor`

Goal: the first curated repo runs on skill-dojo, and `scripts/` is gone.

1. **`init --adopt`**: register every `plugins/*` as a `local` item (mirror/bundle parts
   where the upstream origin is known; otherwise local and listed in a report for later),
   write `registry/` with layout options on (manifest symlinks + flat `skills/` view) and
   branding on (current `com.openai` values), stamp metadata, write `lock.json`.
2. Pin the three MCP servers in `plugins/jenreh-core/.mcp.json` to exact versions
   (looked up from npm/PyPI at adoption time). Adoption reports floating refs; the admin
   picks the versions.
3. **`vendor`** (consumer side, port of `add-skills.sh`): git subtree of a marketplace ref
   or tag into `.agents/<name>`, plus `.agents/skills` and `.claude/skills` symlinks;
   `vendor --update` does the subtree pull. Refuses a dirty tree.
4. In the jenreh repo (separate PR there): delete `scripts/`, switch `Taskfile.yml` to
   `skill-dojo` commands, replace `.github/workflows/validate.yml` with the generated
   `validate-marketplace.yml` (tool pinned by git SHA), create the `staging` branch.

Done: in the jenreh clone, `skill-dojo build && git diff` shows only the intended metadata
additions and MCP pins; `skill-dojo validate` passes; CI passes on a clean runner;
Codex and Claude Code still install every plugin (manual check with
`claude plugin marketplace add` + install of each plugin).

## Phase 3: Sources, mirror, candidate PRs and sync

Goal: the gate works for single upstream plugins and for local changes.

1. **`source add|list|remove`** and **`browse <source>`** with catalog readers for
   `agent_plugins_marketplace`, `claude_marketplace` and `git` (a plain repo with skills
   or plugins), `ref` and `allowlist` support. Remote plugin sources inside an upstream
   catalog are followed and pinned to their own commit.
2. **Resolve and fetch**: ref → commit (`git ls-remote`), fetch at commit, normalize
   (add only: missing Agent Plugins or `.claude-plugin` manifest, metadata; vendor
   LICENSE/NOTICE into `licenses/`). Plugins that cannot be represented without rewriting
   files are rejected with a clear error.
3. **Risk flags** (`risk.py`, pure functions over the approved vs candidate tree): new/changed executables,
   hooks, shell in commands/skills, MCP server add or `command/args/env/url` change,
   new network endpoints (URL scan), changed `allowedTools`/permissions, binaries,
   symlinks escaping the plugin, license missing/changed, upstream metadata-only change.
   Each flag has file + line. Rendered as markdown for the PR body.
4. **`mirror <source> <plugin>`** and **`sync [--item]`**: per item a branch
   `candidate/<item>/<short-sha>`, commit (vendored files, `items.yaml`, `lock.json`,
   upstream metadata), PR into `staging` with diff summary + risk flags. Idempotent: an
   open candidate for the same commit is updated, not duplicated. Quarantined items are
   skipped. Version: mirror keeps upstream `version`.
5. **Local changes as candidates**: `validate` on a PR into `staging` fails when a local
   item's content no longer matches its lock entry; `lock refresh` fixes it and
   `skill-dojo flags --base staging` prints the risk flags (posted as a PR comment by the
   validate workflow).
6. `init` also writes `sync-upstream.yml` (scheduled + `workflow_dispatch`, token from
   Actions secrets, event data only through `env:`).

Done: e2e with fixture repos: add an Agent Plugins and a Claude marketplace, mirror one
plugin → candidate PR (fake `GitHub`) with flags; push an upstream change → `sync`
opens an update PR showing the diff and flags; changed local skill without `lock refresh`
fails validate.

## Phase 4: Bundles, review, promote, release, revoke, clients

Goal: the full lifecycle from candidate to tag, with policy enforcement.

1. **`bundle create|add|remove`**: parts (skill, agent, MCP server) from several sources
   plus local parts; `parts` array in `extensions.<ns>`; each part pinned and hashed; any
   part change → candidate PR with a semver patch bump.
2. **`review list|show|approve|reject|quarantine`**: approve submits a GitHub review and
   merges via `gh`; if branch protection still blocks, report "waiting" and stop.
   Reject closes the PR; quarantine also sets `quarantined: true` in `items.yaml`.
3. **`promote`**: PR `staging` → `main`; reads approvals of every candidate PR merged into
   `staging` since the last promote from the GitHub API (works for merges done on
   github.com); writes `approvals.yaml`, stamps `approved-by/at`, `reviewEvidence`,
   `approvedVersion`; rebuilds catalogs; runs `validate`. Blocks on `riskTier: forbidden`,
   missing reviewer count for `restricted`, channel not in `supportedChannels`.
4. **`release`**: on `main`, tag `marketplace-vYYYY.MM.DD[.N]` with generated notes.
5. **`revoke <item>`**: hotfix PR to `main` (remove or roll back to the last approved
   entry), then a back-merge PR into `staging`; prints affected clients.
6. **`clients add|list|remove`** for `clients.yaml`.

Done: e2e: mirror + bundle of two skills from different sources → approve → promote
stamps correct approvals (including a PR merged "on github.com" in the fake) → release
tag; forbidden item and wrong channel cannot be promoted; revoke lists the client of the
affected tag.

## Phase 5: MCP Registry source

1. `mcp_registry` catalog reader (httpx) for the official MCP Registry API; browse servers.
2. Pin npm/PyPI package to an exact version, OCI to an image digest; recorded as
   `upstreamCommit`/`sourceDigest`.
3. Generate a wrapper plugin (`.mcp.json` + manifest) or add the server as a bundle part.
4. `sync` detects new registry versions → candidate PR through the same path.

Done: e2e against a `pytest-httpserver` fake registry: wrapper plugin and bundle part both
pinned; a new fixture version opens a candidate PR.

## Phase 6: Local web UI (`serve`, `[web]` extra)

Package `skill-dojo-web`. Reflex + appkit-mantine (use `reflex-state-and-architecture`,
`appkit-mantine-reference`, `frontend-design` skills). States build a `Context` once per
session and call the same `skill_dojo_core` functions as the CLI; no logic in state
classes beyond orchestration. Long operations (sync, promote) run as Reflex background
tasks and feed `Context.progress` into the UI. Bind to `127.0.0.1`.
First step is a short spike: running a Reflex app shipped inside an installed wheel
(`rxconfig` with `app_module_import="skill_dojo_web.app"`, `.web` build dir in a user cache
directory), so `skill-dojo serve` works from `uv tool install "skill-dojo[web]"` and not
only from a checkout.
Pages: Sources · Browse/Select (mirror or bundle) · Candidates/review queue (diff, flags,
approve/reject/quarantine) · Marketplace preview (exact catalogs + tree `build` would
write) · Releases (promote, tag, notes) · Clients (edit `clients.yaml`) · Audit (timeline
from git log, PRs, tags). `skill-dojo serve` without the extra prints an install hint.

Done: state unit tests (`reflex-testing-state`); a Playwright smoke run of each page
against a fixture curated repo; approving in the UI merges the fake PR.

## Phase 7: Hardening and first release

1. Full spec verification list as one e2e suite (no network); coverage ≥ 80 %.
2. "Delete the tool" check: a release-tagged fixture repo imports into Codex and Claude
   Code without skill-dojo installed (catalog/manifest schema check + manual install).
3. README and `docs/` (commands, file formats, adoption guide).
4. PyPI Trusted Publishing workflow in skill-dojo for `skill-dojo-core`, `skill-dojo` and
   (opt-in) `skill-dojo-web`; first tagged release of all three.
5. Switch the jenreh repo pin from git SHA to `skill-dojo==X.Y.Z` in its own reviewed PR;
   confirm `uvx skill-dojo==X.Y.Z validate` on a clean runner without the web extra.
6. Prove the release split once: a patch release of core + CLI only, then
   `uv tool install "skill-dojo[web]==X.Y.Z+1"` still resolves the previous web release.

## Per-phase definition of done

Tests first and green, coverage ≥ 80 %, `task lint` clean, no file > 1000 lines,
`code-review` skill run, README/CLAUDE.md updated where affected, memory updated
(decisions such as the `skill-dojo` CLI name, hash scheme, git-SHA pin), one PR per phase.

## Out of scope (v1, from the spec)

Machine lock-down/MDM, a hosted UI or server package with login (prepared for by the core
API rules, not built), detecting which workspace imported which
tag, automated security verdicts (LLM/SAST), hand-editing mirrored content, an `lts`
branch.
