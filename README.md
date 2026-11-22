<div align="center">

# skill-dojo

  **Manages agent plugin marketplaces, skills, and MCP servers in a git repo.**

  ![Version](https://img.shields.io/badge/version-0.0.0-blue)
  [![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE.md)
  [![Python](https://img.shields.io/badge/python-3.14%2B-orange)](https://www.python.org)

  [Packages](#packages) • [Getting Started](#project-initialization) • [Branching](#branching)

</div>

---

skill-dojo turns a GitHub repo into a curated agent plugin marketplace: every mirrored
or local plugin, part and MCP server is pinned to an exact commit, hashed, and changes
only through one reviewed pull request from a work branch. Status: early development, see
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

## How it works

1. `source add` an upstream marketplace; its catalog is cached in `.skill-dojo/cache/`
   (git ignores it) and `browse` reads it from there.
2. `mirror` a whole plugin, or `add-parts` skills, agents, MCP servers or hooks into a
   new or existing local plugin, or `plugin new` and drop files in, then `build`.
3. Every command is one commit on the work branch `skill-dojo/changes` in your
   checkout (created from `origin/main` when needed). Plugin versions are bumped for you.
4. `finish` pushes the branch and opens one PR into `main`. Merging it is the approval.
5. `release` tags `main` and creates a GitHub Release.

## Commands

| Command | What it does |
| --- | --- |
| `skill-dojo init [--name] [--repository] [--tool-git SHA \| --tool-version X.Y.Z]` | Scaffold `registry/`, both catalogs and `.github/workflows/validate-marketplace.yml` |
| `skill-dojo init --adopt [--repository] [--tool-git SHA]` | Turn an existing marketplace into a curated one: every `plugins/*` becomes a local item; name, owner, layout, branding, categories and policies are read from the existing catalogs and manifests; floating MCP refs and likely vendored skills are reported |
| `skill-dojo source add <id> <owner/name or URL> [--type] [--ref] [--allow]` / `list` / `remove` / `allow` / `refresh [id]` | Upstream sources: Agent Plugins or Claude marketplaces, a plain git repo, or the MCP Registry (`--type mcp_registry https://registry.modelcontextprotocol.io`); `add` caches the catalog |
| `skill-dojo browse <source> [--refresh] [--parts] [--search]` | What a source offers, from the cache (`--refresh` fetches again); `--parts` lists each plugin's parts as `source:plugin/kind/name` |
| `skill-dojo mirror <source> <plugin> [--as id]` | Vendor a whole plugin at the pinned upstream commit, with lock entry and metadata. An MCP Registry server becomes a wrapper plugin pinned to the exact npm/PyPI version or OCI image digest |
| `skill-dojo add-parts <plugin> <parts...> [--create] [--description] [--category]` | Copy parts into a local plugin: `source:plugin/kind/name` with kind `skill`, `agent`, `mcp_server` or `hook` (`mcp:<server>/mcp_server/<key>` for the MCP Registry, `local:<plugin>/...` for this repo) |
| `skill-dojo remove-parts <plugin> <kind/name...>` | Remove parts from a local plugin |
| `skill-dojo plugin new <name> [--description] [--category]` | An empty local plugin at `0.1.0`; put files into `plugins/<name>/`, then `build` |
| `skill-dojo build [--check]` | Lock new or edited files of local plugins, bump their versions, regenerate catalogs, manifests, branding, metadata and layout links |
| `skill-dojo version <item> --patch\|--minor\|--major\|--set X.Y.Z` | Set a local plugin's version relative to `main` (mirrors keep the upstream version) |
| `skill-dojo sync [--item]` | Refresh the cached catalogs and commit every moved mirror or plugin with parts onto the work branch (idempotent; quarantined items skipped) |
| `skill-dojo status` | The work branch: ahead/behind `main`, uncommitted files, its PR, changed plugins with old and new version |
| `skill-dojo finish [--level item=patch\|minor\|major\|X.Y.Z] [--no-pr]` | Build, set versions, commit, push and open or update the one PR into `main` (body: versions, pins, risk flags) |
| `skill-dojo release [--notes]` | After the merge: validate `origin/main`, tag `marketplace-vYYYY.MM.DD[.N]` and create a GitHub Release |
| `skill-dojo revoke <item> [--to TAG]` | On the work branch: remove the item, or roll it back to a tag and quarantine it; lists the clients whose ref holds it |
| `skill-dojo clients add <name> <ref> [--contact] [--notes] [--update]` / `list` / `remove` | The hand-kept `registry/clients.yaml` |
| `skill-dojo flags [--base origin/main]` | Risk flags of the working tree against a base, as markdown (the validate workflow posts them on PRs into `main`) |
| `skill-dojo local add plugins/<name>` / `lock refresh [--item]` | Register an existing folder; recompute local lock entries (`build` does this too) |
| `skill-dojo validate` | Agent Plugins / skill checks, untracked folders, drift, floating MCP references, forbidden risk tier |
| `skill-dojo marketplace add <url> [--ref TAG] [--name]` / `update <url> [--ref TAG]` | Consumer side: `git subtree` of a marketplace into `.agents/<name>` plus `.agents/skills` and `.claude/skills` links (replaces `add-skills.sh`) |
| `skill-dojo serve [--port 8080] [--repo <dir>]` | Local web UI on `127.0.0.1` (needs `skill-dojo[web]`): changes, sources, plugins, marketplace preview, releases, clients, audit. It calls the same core functions as the CLI |

### Curated repo files

- `registry/config.yaml`: name, namespace, tool pin, `work_branch`, layout and branding
- `registry/items.yaml`: tracked plugins (`mirror` or `local`, with optional `parts`)
- `registry/lock.json`: per item the upstream repo/commit/path, `treeSha256` and per
  file `sha256` (plus `normalizedSha256` for `SKILL.md` and `plugin.json`, so stamped
  metadata is never drift)
- `registry/sources.yaml`, `channel-policy.yaml` (default risk tier and data
  classification), `clients.yaml`
- `.skill-dojo/cache/`: cached upstream catalogs and checkouts; it ignores itself
- Older repos with `kind: bundle`, `approvals.yaml` or staging channels still load;
  `build` rewrites them

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
