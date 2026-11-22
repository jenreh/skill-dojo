<div align="center">

# skill-dojo

  **Manages agent plugin marketplaces, skills, and MCP servers in a git repo.**

  ![Version](https://img.shields.io/badge/version-0.0.0-blue)
  [![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE.md)
  [![Python](https://img.shields.io/badge/python-3.14%2B-orange)](https://www.python.org)

  [Packages](#packages) • [Getting Started](#project-initialization) • [Branching](#branching)

</div>

---

skill-dojo turns a GitHub repo into a curated agent plugin marketplace: every mirrored,
bundled or local plugin and MCP server is pinned to an exact commit, hashed, and changes
only through a reviewed pull request. Status: early development, see
[the design](spec/2026-11-21-curated-marketplace-design.md) and
[the plan](spec/2026-11-21-curated-marketplace-plan.md).

## Packages

| Package | PyPI name | What it is |
| --- | --- | --- |
| `components/skill-dojo-core` | `skill-dojo-core` | All behaviour, front-end neutral |
| `components/skill-dojo-cli` | `skill-dojo` | The `skill-dojo` command (Typer) |
| `components/skill-dojo-web` | `skill-dojo-web` | Local web UI (Reflex), the `[web]` extra |

```sh
uv run skill-dojo --help
```

## Commands available so far

| Command | What it does |
| --- | --- |
| `skill-dojo init [--name] [--repository] [--tool-git SHA \| --tool-version X.Y.Z]` | Scaffold `registry/`, both catalogs and `.github/workflows/validate-marketplace.yml` |
| `skill-dojo local add plugins/<name> [--category]` | Register a local plugin: item, `lock.json` entry, provenance metadata, catalogs |
| `skill-dojo lock refresh [--item]` | Recompute the lock entry of a local plugin after an edit |
| `skill-dojo build [--check]` | Regenerate catalogs, missing manifests, branding, metadata and layout links |
| `skill-dojo validate` | Agent Plugins / skill checks, untracked folders, drift, floating MCP references |
| `skill-dojo init --adopt [--repository] [--tool-git SHA]` | Turn an existing marketplace into a curated one: every `plugins/*` becomes a local item; name, owner, layout, branding, categories and policies are read from the existing catalogs and manifests; floating MCP refs and likely vendored skills are reported |
| `skill-dojo source add <id> <owner/name or URL> [--type] [--ref] [--allow]` / `list` / `remove` | Upstream sources: Agent Plugins or Claude marketplaces, a plain git repo, or the MCP Registry (`--type mcp_registry https://registry.modelcontextprotocol.io`) |
| `skill-dojo serve [--port 8080] [--repo <dir>]` | Local web UI on `127.0.0.1` (needs `skill-dojo[web]`) for the repo at `--repo` (default: the current directory; `~` is expanded): review queue, sources, bundles, marketplace preview, releases, clients, audit. It calls the same core functions as the CLI; the Reflex frontend is built in `~/.cache/skill-dojo/web` |
| `skill-dojo browse <source> [--search]` | What a source offers at its current ref (remote plugin sources included); for the MCP Registry, the latest version of each server and why it cannot be pinned |
| `skill-dojo mirror <source> <plugin> [--as id]` | Candidate PR into `staging`: vendored files pinned to the upstream commit, lock entry, metadata, risk flags. An MCP Registry server becomes a wrapper plugin (`plugin.json` + `.mcp.json`) pinned to the exact npm/PyPI version or the OCI image digest; it is also a bundle part as `mcp:<server name>/mcp_server/<key>` |
| `skill-dojo sync [--item]` | A candidate PR for every mirror and bundle on `staging` whose upstream moved (idempotent; quarantined items skipped) |
| `skill-dojo bundle create <name> [parts...] [--description] [--category]` / `add <name> <parts...>` / `remove <name> <kind/name...>` | A bundle plugin of parts `source:plugin/kind/name` (kind `skill`, `agent` or `mcp_server`; source `local` = this repo's own plugins), each pinned and locked; every change is a candidate PR with a patch bump |
| `skill-dojo review list` / `show <pr>` / `approve <pr>` / `reject <pr> [--reason]` / `quarantine <pr>` | Candidate PRs: approve submits a GitHub review and merges (reports `waiting` while branch protection blocks); quarantine closes it and opens a PR setting `quarantined: true` |
| `skill-dojo promote` | PR `staging` → `main`: reads approvals of merged candidate PRs from GitHub (also merges done on github.com), writes `approvals.yaml`, stamps `approved-by`/`approved-at`/`reviewEvidence`; blocked by `riskTier: forbidden`, too few reviewers, or `stable` missing from `supported_channels` |
| `skill-dojo release` | Tag `origin/main` as `marketplace-vYYYY.MM.DD[.N]` with notes (added, updated, removed items) after validating it |
| `skill-dojo revoke <item> [--to TAG] [--reason]` | Hotfix PR into `main` that removes the item (or rolls it back to a tag and quarantines it), a back-merge PR into `staging`, and the clients whose ref holds the item |
| `skill-dojo clients add <name> <ref> [--contact] [--notes] [--update]` / `list` / `remove` | The hand-kept `registry/clients.yaml` |
| `skill-dojo flags [--base origin/staging]` | Risk flags of the working tree against a base, as markdown (the validate workflow posts them on PRs into `staging`) |
| `skill-dojo vendor <url> [--ref TAG] [--name] [--update]` | Consumer side: `git subtree` of a marketplace into `.agents/<name>` plus `.agents/skills` and `.claude/skills` links (replaces `add-skills.sh`) |

### Curated repo files

- `registry/config.yaml`: name, namespace, tool pin, layout and branding options
- `registry/items.yaml`: tracked plugins (`local`, `mirror`, `bundle`)
- `registry/lock.json`: per item the upstream repo/commit/path, `treeSha256` and per
  file `sha256` (plus `normalizedSha256` for `SKILL.md` and `plugin.json`, so stamped
  metadata is never drift)
- `registry/sources.yaml`, `approvals.yaml`, `channel-policy.yaml`, `clients.yaml`

## Project Initialization

Before initializing the project, install these required tools:

1. `uv`: [installation instructions](https://docs.astral.sh/uv/getting-started/installation/)
2. `task`: [installation instructions](https://taskfile.dev/installation/)

After both tools are installed, run:

```sh
task init
```

This installs the required Python version, syncs dependencies, and installs the pre-commit hooks.

## Security

See [SECURITY.md](SECURITY.md) for the secure defaults and the checklist to go through
before a deployment.

## Branching

See [BRANCHING.md](BRANCHING.md) for the repository branch naming policy.
