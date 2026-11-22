# Curated Agent Plugin Marketplace Tool: Design

Date: 2026-11-22 (rev. 2). Status: approved. Rev. 2 replaces staging, candidate PRs,
approvals and promote with one work branch, automatic plugin versions and a manual
release.

## Where things live (decided by the user)

- **The tool is `skill-dojo`** (command), in its own repo `jenreh/skill-dojo` at
  `/Users/jens/Workspace/projekte/skill-dojo`. That repo holds the CLI and the web UI as
  three uv workspace packages: `skill-dojo-core` (all logic), `skill-dojo` (the CLI,
  console script `skill-dojo`) and `skill-dojo-web` (the Reflex UI, the `[web]` extra).
- **The CLI is published to PyPI as `skill-dojo`**. GitHub Actions in a curated repo run
  it with `uvx skill-dojo==X.Y.Z <command>`. No checkout of the tool repo is
  needed.
- **A curated repo is a backend only**: plain files, a catalog, plugins, `registry/` and
  workflows. **It contains no scripts.** Everything it needs is a `skill-dojo` command.
- **This repo (`jenreh/agent-skills`) is the first curated repo.** Adopting it is part of
  the work. Its `scripts/` folder (`validate_skills.py`, `validate_plugins.py`,
  `codex_metadata.py`, `link-plugins.sh`, `add-skills.sh`) is ported into skill-dojo and then
  deleted. `Taskfile.yml` and `.github/workflows/validate.yml` are switched to `skill-dojo`
  commands, or replaced by the generated workflows.

## Context and why

Today, skills from other marketplaces (deepeval, pydantic-ai, frontend-design and others)
are copied into the jenreh plugins by hand. The pain: **the copies go stale without anyone
noticing.** There is also a bigger goal: a team of developers should use only skills,
agents and MCP servers that come from one curated marketplace. Everything in it is
**pinned to an exact version and explicitly approved** for security reasons.

The tool turns any GitHub repo into that kind of curated marketplace. The GitHub repo is
the only backend: all state, history and approvals live in it as plain files and commits.
The jenreh `agent-skills` repo is the first real user, but the tool is generic.

## Goals

1. Add upstream sources (Agent Plugins marketplaces, plain git repos, the MCP Registry),
   browse what they offer from a local cache, and select plugins, skills, agents, MCP
   servers and hooks.
2. Two kinds of items, **all behind the same gate** (decided by the user):
   - **Mirror**: copy one upstream plugin as it is.
   - **Local**: the team's own plugin. It holds hand-written files and, optionally,
     **parts** (a skill, an agent, an MCP server or a hook) copied from one or more
     upstream plugins. Most jenreh plugins are local plugins without parts. A change to a
     local plugin goes through the same work branch and PR as any other change, with
     risk flags, a `lock.json` entry (the content hash, with `upstreamCommit` = the
     repo's own commit) and the same validation. The MCP pinning rule applies too.
     Today's unpinned `npx -y @upstash/context7-mcp` in `jenreh-core/.mcp.json` must be
     pinned when the jenreh repo is adopted. `validate` fails on any folder under
     `plugins/` that the registry does not track.
3. **Pin every item** to an exact upstream commit, with a recorded archive SHA-256.
   Nothing reaches `main` until someone approves it.
4. **One work branch.** Every change (a new mirror, new parts, a new plugin, an upstream
   update, a revocation) is a commit on one branch in the admin's checkout
   (`skill-dojo/changes` by default). A scheduled GitHub Action checks upstream and
   writes each new upstream version as a commit on the same branch, never as an
   automatic update of `main`. **One PR into `main`** carries the diff plus
   **automatic risk flags**. Merging it is the approval.
5. **Releases.** After the merge, an admin creates a release (CLI or UI): an immutable tag
   (`marketplace-vYYYY.MM.DD[.N]`) plus a GitHub Release with notes. Clients import
   `main` or a pinned tag.
6. **Publish to several clients.** Agent Plugins 1.0 is the canonical format, written to
   `.agents/plugins/marketplace.json` (ChatGPT, Codex, Copilot). From the same source the
   tool also generates the `.claude-plugin/` manifests for Claude Code.
7. **A CLI** manages everything, and `serve` starts a **local web UI** for the same tasks.
8. **Audit and revocation.** Every sync, change, merge, release and revocation can be
   traced in git. A hand-kept list of clients shows who must be warned when something is
   revoked.
9. **The MCP Registry is a v1 source** (decided by the user). Browse the official MCP
   Registry. A server entry (npm, PyPI or OCI package) is pinned to an exact package
   version or image digest, and the pinned value is recorded as its `upstreamCommit` /
   `sourceDigest`. It becomes a generated wrapper plugin (one `.mcp.json` plus a
   manifest) or a part inside a local plugin. Updates are detected by new registry
   versions and land on the work branch like every other upstream change.
10. **Versions are kept by the tool.** A changed local plugin gets a patch bump
    automatically. The admin can choose minor, major or an exact version instead. Mirrors
    keep the upstream version.

## Non-goals (v1)

- Locking down developer machines (managed settings, MDM). The tool only curates. Lock-down
  is handled elsewhere.
- A hosted, shared web console with its own login. In v1 the UI is local only.
- Detecting which workspace imported which tag. ChatGPT, Codex and Claude Code don't report
  this, so clients are recorded by hand.
- A full automated security verdict (an LLM or SAST judging the code). v1 gives risk flags
  and humans decide.
- Editing mirrored content by hand (see "Calls made").
- Per-item approvals, several reviewers per item and release channels (beta, stable).
- An automatic release when the PR is merged, and one semver for the whole registry.

## Anti-goals (a failure even if it works)

- **Lock-in.** The curated repo must stay plain, standard files: valid Agent Plugins and
  Claude manifests, readable YAML, normal git history. Someone must be able to hand-edit it,
  or stop using the tool entirely, and still have a working marketplace. No hidden state, no
  database, no custom format that only this tool can read.
- Unapproved content reaching `main` or a tag through any path. Content reaches `main`
  only through the reviewed PR, and the repo's branch protection enforces the review.
- Setup that takes more effort than copying skills by hand did.

## Constraints

- The backend is the GitHub repo itself. Credentials are never stored in it. They live in
  GitHub Actions secrets (for the sync job) or in the admin's local env and `gh auth`.
- Each admin runs the tool against their own local clone. Identity and permissions come
  from their GitHub account (`gh`). The repo's branch protection and required reviews are
  the real access control.
- Content is copied in (vendored). No git submodules, and no catalog entries that point
  straight at upstream. Every catalog entry uses `"source": {"source": "local", ...}`.

## Decided by the user

- Stack: **Python 3.14, a Typer CLI** (installed with `uv tool install`), and **Reflex +
  appkit-mantine** for the web UI. `serve` starts the UI.
- Sync: a scheduled GitHub Action writes upstream updates as commits on the work branch
  and opens or updates the one PR into `main`. Merging the PR is the approval.
- A reviewer sees the diff plus risk flags.
- The work branch lives in the admin's own checkout. When it has been merged, the next
  change starts a fresh one from `main`.
- Versions: an automatic patch bump, a manual override, and a "finish" step that lists
  every changed plugin with a major, minor or patch choice. Bumps land in the PR, never as
  a commit on `main` after the merge.
- Release is manual (`skill-dojo release` or a button in the UI).
- `local` and `bundle` are one kind, `local`. Kinds left: `mirror` and `local`.
- Revocation is a normal change on the work branch.
- Upstream catalogs are cached in the curated repo in a local folder that git ignores,
  so browsing is fast. `sync` updates the cache.
- Clients are a hand-kept `registry/clients.yaml`, edited through the UI.
- The UI is local only in v1.
- Output: Agent Plugins plus Claude Code manifests.
- Generic tool. The jenreh repo is the first user.
- The user's reference flow, repo layout, catalog entry shape, `sources.yaml` example,
  domain objects and UI pages (given in the conversation) are the basis below.

## Curated repo layout (what the tool reads and writes)

```
<curated-repo>/
├── .agents/plugins/marketplace.json     # canonical catalog (Agent Plugins / Codex)
├── .claude-plugin/marketplace.json      # generated for Claude Code
├── plugins/<name>/
│   ├── plugin.json                      # Agent Plugins manifest
│   ├── .claude-plugin/plugin.json       # generated (or symlink, as the jenreh repo does)
│   ├── skills/ .mcp.json commands/ hooks/ agents/ assets/ ...
├── registry/
│   ├── config.yaml           # namespace, pinned skill-dojo version, work_branch, layout and branding options
│   ├── sources.yaml          # upstream sources, refs, allow-lists, schedule
│   ├── items.yaml            # what is mirrored or local, from where, pinned at what
│   ├── channel-policy.yaml   # default risk tier and data classification
│   ├── clients.yaml          # hand-kept: workspace or client -> ref/tag in use
│   └── lock.json             # provenance: upstream repo, commit, path, sha256 per file/archive
├── .skill-dojo/cache/        # local only: cached upstream catalogs and checkouts (ignores itself)
└── .github/workflows/
    ├── validate-marketplace.yml
    └── sync-upstream.yml
```

Every `registry/` file is readable and editable by hand. The tool rebuilds both
marketplace catalogs from `plugins/` and `registry/`, so a hand edit followed by
`<tool> build` gives a consistent result.

`.skill-dojo/cache/` holds one folder per source and commit
(`sources/<id>/<commit>/` with the checkout and an `index.json` of the plugins and their
parts). It contains its own `.gitignore` with `*`, so git never sees it and the repo's
own `.gitignore` is not touched. Deleting the folder only costs a fetch.

### Catalog entry (example)

```json
{
  "name": "github-pr-reviewer",
  "description": "Reviews pull requests using repository conventions.",
  "version": "1.4.2",
  "source": { "source": "local", "path": "./plugins/github-pr-reviewer" },
  "policy": { "installation": "AVAILABLE", "authentication": "ON_USE" },
  "category": "Developer Tools"
}
```

### Source record (example)

```yaml
sources:
  - id: openai-community-plugins
    type: agent_plugins_marketplace     # | claude_marketplace | git | mcp_registry (all v1)
    repository: openai/community-plugins
    marketplace_path: .agents/plugins/marketplace.json
    ref: main
    allowlist: [grafana-observability, react-native-to-swiftui]
```

## Provenance metadata in skills and plugins (decided by the user)

Every vendored skill and plugin carries its own origin and license facts inside its
standard files. Then the facts travel with the content even when someone copies a
folder out of the repo, and they are readable without the tool (anti-lock-in). The
approval itself is the merged PR in git history; it is not stamped into the files.

**Skills: `SKILL.md` frontmatter `metadata`.** It is a flat map of string keys to string
values. Values are always strings: no nested objects, arrays, booleans or numbers. Every
key uses a namespaced prefix. Custom keys never go at the top level of the frontmatter.
No secrets or large policy blobs go here.

```yaml
---
name: github-pr-reviewer
description: Reviews pull requests using repository conventions. Use when reviewing a GitHub pull request.
license: Apache-2.0
metadata:
  acme.registry/id: acme:github-pr-reviewer
  acme.registry/version: 1.4.2
  acme.registry/source-marketplace: openai/community-plugins
  acme.registry/source-plugin: grafana-observability
  acme.registry/source-path: plugins/grafana-observability/skills/github-pr-reviewer
  acme.registry/source-commit: 8f2c1a9...
  acme.registry/source-license: Apache-2.0
  acme.registry/risk-tier: standard
  acme.registry/data-classification: internal
---
```

**Plugins: `plugin.json` `extensions.<namespace>`.** The Agent Plugins top level is closed
(`$schema`, `name`, `displayName`, `version`, `description`, `author`, `homepage`,
`repository`, `license`, `keywords`, `extensions`), so all custom data goes under one
extension key. Here, JSON types such as arrays are allowed.

```json
"extensions": {
  "com.acme.registry": {
    "registryId": "acme:github-pr-reviewer",
    "kind": "mirror",
    "upstreamMarketplace": "openai/community-plugins",
    "upstreamPlugin": "grafana-observability",
    "upstreamCommit": "8f2c1a9...",
    "upstreamVersion": "1.4.2",
    "upstreamLicense": "Apache-2.0",
    "riskTier": "standard",
    "dataClassification": "internal"
  },
  "com.openai": { "...": "existing client extensions are kept untouched" }
}
```

**Field set (decided by the user).** The same facts are used in both places: camelCase
under `extensions.<ns>`, and kebab-case string keys under the skill `metadata` prefix.

| Field | Purpose |
|---|---|
| `registryId` | Stable internal identity, e.g. `acme:github-pr-reviewer` |
| `kind` | `mirror` or `local` |
| `upstreamMarketplace` | Original source marketplace, repository or MCP Registry |
| `upstreamPlugin` | Original plugin, skill or server identifier |
| `upstreamRef` | Upstream tag, release or branch that was tracked |
| `upstreamCommit` | Exact source revision (or package version / image digest for MCP Registry) |
| `upstreamVersion`, `upstreamLicense` | As declared upstream |
| `sourceDigest` | SHA-256 of the vendored plugin or skill content |
| `riskTier` | `low`, `standard`, `restricted` or `forbidden` |
| `dataClassification` | `public`, `internal`, `confidential` (list configurable) |
| `allowedTools` | Explicit tool and network permissions |
| `deprecation` | Replacement and removal date, when it applies |

In skill `metadata`, the list value `allowed-tools` is a comma-separated string, and
`deprecation` is two keys (`deprecation-replacement`, `deprecation-removal-date`), because
values must be strings. The portable set lives in the files. The full record lives in the
registry, as described below.

**Where to store what.** The paste says "registry database". Here that is the repo
itself, because there is no database:

| Data | In the plugin or skill folder | In the registry (this repo) |
|---|---|---|
| Identity, source, version | Yes, the field set above | `items.yaml`, `lock.json` |
| Approval, review history, reviewer comments | No | The merged work-branch PR (its reviews and comments) |
| Scan reports, risk-flag output, large fixtures | No | PR body and comment, GitHub Actions artifact |
| Secrets, API keys, tenant config | Never | Never in the repo: GitHub Actions secrets or local env |
| Org policy defaults | No | `registry/channel-policy.yaml` |
| Installation state per workspace | No | `registry/clients.yaml` (hand-kept) |

**Policy effects.** `riskTier: forbidden` fails `validate`, so such an item cannot reach
`main`. A changed `allowedTools`, or an upstream metadata change on its own, is a risk
flag.

For a **local plugin with parts**, the plugin extension has `"kind": "local"` and a
`parts` array. It has one entry per included skill, agent, MCP server or hook, each with
its own upstream marketplace, plugin, path, commit and license. Each included skill also
carries its own `metadata` as above.

Rules:
- **Namespace is configurable per curated repo** (`registry/config.yaml`), for example
  `acme.registry/` for skills and `com.acme.registry` for plugins. Default is derived
  from the marketplace name.
- **Merge, never replace.** Upstream frontmatter, upstream `metadata` keys and other
  `extensions` (for example `com.openai`) are kept as they are. The tool only adds or
  overwrites keys in its own namespace.
- **Licenses.** The upstream `license` value is copied, and any upstream LICENSE or NOTICE
  file is vendored into the plugin (`licenses/`, as the jenreh repo already does). A
  missing upstream license, or one that changed, is a risk flag.
- **When fields are written.** Upstream fields (`source-*`, `upstream*`, license) are
  written by the command that vendors the content, so the reviewer sees them in the PR.
  `riskTier` and `dataClassification` come from `items.yaml` (defaults from
  `channel-policy.yaml`); a reviewer can change them on the work branch.
- **Drift and hashes.** `lock.json` keeps the upstream content hashes. Hashing and drift
  checks normalize away the tool's own namespaced keys, so stamping metadata is not
  reported as drift, while any other change to a mirrored file is.
- `lock.json` is the full machine record (per-file hashes, archive SHA-256). The in-file
  metadata is the human-readable copy that travels with the content. `validate` checks
  that the two agree.

### Versions

- An item is **changed** when its lock `treeSha256` (or its file list) differs from
  `origin/main`, or when it is new or removed.
- **Local plugins.** When a local plugin is changed and its `plugin.json` version still
  equals the version on `origin/main`, `build` sets it to the patch bump. When the
  version on the branch is already higher (set by hand or by an earlier bump), it stays.
  A new plugin starts at `0.1.0`.
- `version <item> --patch|--minor|--major|--set X.Y.Z` sets the version relative to the
  version on `origin/main`. `--set` must be semver and greater. The version lives only
  in `plugin.json` on the branch; there is no extra state file. A version edit refreshes
  the lock, so drift checks stay clean.
- **Mirrors** keep the upstream `plugin.json` version. It is never bumped or set by the
  tool. A mirror whose upstream has no version has none (see "Calls made").
- `finish` lists every changed plugin with its version on `main`, its new version and a
  major, minor or patch choice.

## Domain model

| Object | Lives in | Purpose |
|---|---|---|
| Source | `sources.yaml` + `.skill-dojo/cache/` | An upstream marketplace, git repo or MCP Registry, and its cached catalog |
| Item | `items.yaml` | A mirror (one upstream plugin) or a local plugin (own files plus optional parts), each with its refs |
| Part | `items.yaml` + `lock.json` | One skill, agent, MCP server or hook inside a local plugin, pinned to its upstream commit |
| WorkBranch | the branch `skill-dojo/changes` + its one PR into `main` | All changes that are not yet approved |
| PendingVersion | computed from the branch and `origin/main` | A changed item with its old and new version |
| Release | git tag on `main` + GitHub Release | A tagged state of the catalogs and the plugin tree, with notes |
| Client | `clients.yaml` | Who uses which ref or tag (hand-kept) |
| AuditEvent | git history (commits, PRs, tags) | Derived, never stored separately |

## Flow

```
source add ─► cache (catalog + part index) ─► browse
   ├─► mirror whole plugin ───────────────────────────┐
   ├─► pick parts ─► into a new or existing local plugin ┤
   └─► plugin new ─► add files by hand ─► build ────────┤
                                                       ▼
          commits on the work branch (one per command; sync adds upstream updates)
                                                       ▼
          finish: build, versions, risk flags ─► push ─► one PR into main
                                                       ▼
          review and merge on GitHub (branch protection) ─► release: tag + GitHub Release
```

**Work branch rules.**

- The name comes from `registry/config.yaml` (`work_branch`, default
  `skill-dojo/changes`).
- Every writing command starts by making sure the admin's checkout is on the work branch:
  - Already on it: use it.
  - Otherwise the working tree must be clean, or the command stops and names the dirty
    files. The tool fetches `origin`. If `origin/<work>` exists and is not fully merged
    into `origin/main`, it checks that out (tracking). If it is merged or missing, it
    creates the branch fresh from `origin/main`. A local work branch with commits that are
    not on `origin/main` yet is kept and checked out, so unpushed work is never lost.
  - The tool never force-pushes and never rewrites history the admin pushed.
- Each writing command makes **one commit** (`skill-dojo: <action> <item>`, with
  `--no-verify`, because local hooks must never run on upstream content). Hand edits are
  committed by `finish`, or by the admin.
- `sync` (CLI and scheduled workflow) writes upstream updates into the same work branch:
  one commit per moved mirror or local plugin with parts. It skips `quarantined` items and
  is idempotent. It also refreshes the cached catalog of every source.
- `finish [--level item=patch|minor|major] [--no-pr]` runs `build` and the version step,
  commits what is left, pushes the branch and opens or updates the one PR into `main`.
  The PR body lists every changed item with its old and new version, kind, upstream pin
  and the risk flags against `origin/main`. `--no-pr` only pushes, and the admin opens
  the PR by hand.
- `status` shows the work branch: whether it exists, commits ahead of and behind
  `origin/main`, dirty files, the PR (number, state, link) and the changed items with
  their pending versions.

**Revocation** is a normal change on the work branch. `revoke <item>` removes the item,
or with `--to TAG` rolls it back to its content at that tag and sets `quarantined: true`.
It reports the clients in `clients.yaml` whose ref still holds the revoked content. To
get it out fast, finish and merge the PR on its own.

**Quarantine.** `quarantined: true` in `items.yaml` only makes `sync` skip the item. The
item stays at its pinned commit until the flag is cleared.

**Release** (manual). `release` requires that `origin/main` validates and that `build
--check` is clean there. It tags `marketplace-vYYYY.MM.DD[.N]`, writes notes (added,
updated with old → new version, removed) and creates a GitHub Release for the tag. It
refuses when `origin/main` has not changed since the last tag.

**Migration.** Loading `items.yaml` accepts `kind: bundle` and treats it as `local`, with
its parts kept. `build` rewrites it as `local`. `approvals.yaml` and the `channels` and
`reviewers` keys of `channel-policy.yaml` are ignored when read and removed by `build`.
Existing repos keep working.

## Risk flags (shown in the PR body and in the UI)

Computed from the diff between `origin/main` and the work branch, for example: new or
changed executable scripts, hooks, shell commands in commands or skills, new MCP servers or
changes to their `command`/`args`/`env`/URL, new network endpoints, changed permissions or
allowed tools, binary files, symlinks that point outside the plugin, license changes, a
missing or changed upstream license. Each flag points to file and line. Flags inform the
reviewer. They never block on their own. Blocking is the job of branch protection and
validation. The flags appear in the work-branch PR body, as a PR comment from the
validate workflow, and on the Changes page.

## CLI surface

`init [--adopt]` (scaffold a curated repo), `source add|list|remove|refresh|allow`,
`browse <source> [--refresh]`, `mirror <source> <plugin> [--as id]`,
`add-parts <plugin> <parts...> [--create]`, `remove-parts <plugin> <kind/name...>`,
`plugin new <name>`, `local add <dir>`, `lock refresh`, `build [--check]`, `validate`,
`flags [--base]`, `version <item> --patch|--minor|--major|--set X.Y.Z`, `sync [--item]`,
`status`, `finish [--level item=level] [--no-pr]`, `release`, `revoke <item> [--to TAG]`,
`clients add|list|remove`, `vendor` (consumer side, replaces `add-skills.sh`), `serve`
(needs `skill-dojo[web]`).

Parts use `source:plugin/kind/name` with `kind` one of `skill`, `agent`, `mcp_server` or
`hook` (`mcp:<server>/mcp_server/<key>` for the MCP Registry, `local:<plugin>/...` for
this repo's own plugins). A hook part is one event of the upstream `hooks/hooks.json` (or
the manifest's `hooks`) plus the script files it references through
`${CLAUDE_PLUGIN_ROOT}`. It is refused when a referenced file is missing or outside the
plugin, or when the target already has that event.

## Web UI pages (local, `serve`)

Changes (work-branch status, changed plugins with a major/minor/patch/custom version
choice, risk flags, "Finish & open PR", the PR link and state) · Sources (sources, add a
source, the cached plugins of each source with "Mirror whole plugin" and an expand of its
skills, agents, MCP servers and hooks with an "Add to plugin" dialog) · Plugins (every
item with kind, version and parts; "New plugin" with the folder path to put files in and
a "Scan for new files" button, which runs `build`) · Marketplace preview (the exact
catalogs and tree that would be committed) · Releases (commits on `origin/main` since the
last tag, notes preview, "Create release", past releases) · Clients · Audit (timeline
built from git).

## Reuse from the jenreh repo (port into skill-dojo, then delete here)

- `scripts/validate_plugins.py`: Agent Plugins 1.0 and MCP schema checks (stdlib, mirrors
  `agent-plugins.org/schemas/1.0.0/*`). Port it into the tool's validation module.
- `scripts/codex_metadata.py`: builds `.agents/plugins/marketplace.json` and the
  `agents/openai.yaml` stubs from manifests. This is the basis of `build`.
- `scripts/link-plugins.sh`: the symlink approach (one manifest per plugin, shared by
  Claude and Agent Plugins paths, plus the flat `skills/` view). It becomes the layout
  options of `build` (see call 10).
- `scripts/validate_skills.py`, `.github/workflows/validate.yml`: the basis for
  `validate-marketplace.yml`.
- `scripts/add-skills.sh`: vendors the marketplace's skills into a *consumer* project
  repo (git subtree into `.agents/agent-skills`, plus `.agents/skills` and
  `.claude/skills` symlinks). It becomes `skill-dojo vendor` (my call).

## Calls made (not decided by the user, please check)

1. **The web UI is an optional extra.** `pip install skill-dojo` / `uvx skill-dojo` installs only the
   CLI (Typer, PyYAML, httpx, and similar). Reflex and appkit-mantine come with
   `skill-dojo[web]`, which `skill-dojo serve` needs. This keeps `uvx` in Actions fast and keeps
   web dependencies out of CI.
1a. **No database in skill-dojo.** The kit-template scaffold brings in Postgres, SQLAlchemy,
   Alembic and appkit-user (login, roles, `bootstrap_admin.py`). All state lives in the
   curated repo and the UI is local only, so these are removed. Reflex runs without a
   database, and identity comes from `gh auth`. Other template parts (devcontainer,
   pre-commit, Taskfile, CI, bump-my-version) are kept.
2. **Mirrors are never hand-edited.** To change a mirror, you create your own local
   plugin and add its parts. A hand edit inside a mirrored folder is caught by `validate`
   as drift against `lock.json`.
3. **Parts copy exact pinned files** of each picked skill, agent, MCP server or hook into
   a local plugin. Any part's upstream change becomes a `sync` commit on the work branch,
   and the plugin gets a patch bump. A hand edit inside a local plugin, parts included, is
   taken into the lock by `build`; the risk flags against `main` show it in the PR.
4. **Approval = merging the one PR into `main`.** Git is the single source of truth, and
   the audit trail comes from git history. The tool never merges and never bypasses
   branch protection.
5. **Version numbers**: a mirror keeps the upstream `version`. A local plugin uses semver
   and gets a patch bump once per work branch when it changes, or the level chosen in
   `finish` or `version`. A mirror whose upstream has no version gets none, because
   writing one would change upstream bytes. Release tags are date-based.
6. **MCP servers**: vendored as `.mcp.json` inside a plugin. Pinning means pinning the
   package version, image digest or commit that the server config references. A floating
   reference (`latest`, no version) is a validation error.
7. **Credentials**: for the sync Action, a GitHub token from Actions secrets. Locally,
   `gh auth`. Private upstreams use the same token.
8. **Normalizing upstream content.** `lock.json` hashes the **upstream bytes**.
   Normalizing only *adds* things: missing manifests (an Agent Plugins `plugin.json` for a
   Claude-only plugin, or `.claude-plugin/` for an Agent-Plugins-only one) and the tool's
   namespaced metadata. Claude-only parts (hooks, commands, agents) are kept as they are.
   Agent Plugins allows companion surfaces like these. Remote plugin sources in upstream
   catalogs (another repo, a git URL) are followed and pinned to their own commit. A plugin
   that cannot be represented without rewriting its files is rejected with a clear
   validation error.
9. **skill-dojo is pinned in the curated repo.** `init` writes workflows that run
   `uvx skill-dojo==X.Y.Z` at an exact version, also recorded in `registry/config.yaml`. So skill-dojo
   has tagged PyPI releases from the start (Trusted Publishing from the skill-dojo repo's CI).
   Upgrading skill-dojo in a curated repo is its own reviewed PR.
10. **What `build` generates.** Both marketplace catalogs, the missing per-plugin
    manifests, the lock entries of local plugins (new or changed files) and their version
    bumps. Per-repo branding (icon, brand color, the `extensions.com.openai`
    interface block, `agents/openai.yaml` stubs) is generated only if
    `registry/config.yaml` asks for it, ported from `codex_metadata.py`. Because the scripts
    go away, `build` must also do what `link-plugins.sh` does today, as **layout options**
    in `registry/config.yaml`: manifest symlinks (`plugin.json` →
    `.claude-plugin/plugin.json`, `mcp.json` → `.mcp.json`) and the flat `skills/<name>`
    symlink view. Default for a new repo: off. The jenreh repo turns them on. The hardcoded
    plugin list and descriptions in `link-plugins.sh` become data that is read from
    `items.yaml` and the manifests.
11. **The cache lives in the repo.** `.skill-dojo/cache/` ignores itself through its own
    `.gitignore`. A cached checkout is reused only when its `HEAD` is exactly the pinned
    commit. The cache is a speed-up, never a source of truth: the ref is resolved against
    the remote every time something is vendored.

## Left to the builder

Module layout, CLI command names, the exact `items.yaml`, `lock.json` and
`channel-policy.yaml` schemas, how to fetch upstream (git sparse checkout or tarball API),
how risk flags are detected, the Reflex page design within appkit-mantine, test strategy
(TDD per the jenreh-python skills), and packaging.

## Verification (what "done" looks like)

- `init` a fresh test repo and push it. `source add` two upstreams (one Agent Plugins
  marketplace, one Claude marketplace); the catalogs are cached. `browse` lists them from
  the cache. `mirror` one plugin, `add-parts --create` two skills from different sources
  into a new local plugin, and `plugin new` a third plugin and drop a skill into it by
  hand, then `build`. Every command is one commit on `skill-dojo/changes`.
- `finish` pushes the branch and opens one PR into `main` with risk flags. Every changed
  local plugin has a higher version than on `main`; the mirror keeps its upstream
  version; the PR body lists them.
- Merge the PR. The next change creates a fresh work branch from `main`. A push upstream
  (in a fixture repo) followed by `sync` adds a commit to the open work branch and
  updates the same PR. `release` creates the tag and a GitHub Release. Both catalogs
  validate with the ported validators.
- Hand-edit `registry/` and a catalog, run `build` and `validate`: the result is consistent.
  Delete the tool: the repo still imports into Codex and Claude Code.
- `source add` the MCP Registry, add one server as a wrapper plugin and one as a part of a
  local plugin, both pinned. A new registry version (from a fixture) is picked up by
  `sync`.
- Change a local skill: it goes through the work branch like upstream items. An untracked
  folder under `plugins/` fails `validate`. An item with `riskTier: forbidden` fails
  `validate`.
- Change a mirrored file by hand: `validate` reports drift. Stamping namespaced metadata
  does not.
- An old repo with `kind: bundle` items, `approvals.yaml` and staging channels still
  loads; `build` rewrites it to the new form.
- Every vendored `SKILL.md` has string-only, namespaced `metadata` with source and license.
  Every `plugin.json` has `extensions.<namespace>` with upstream and risk fields.
  Upstream frontmatter and other extensions are unchanged. Both pass the Agent Skills and
  Agent Plugins schema checks.
- Unit tests per module. An end-to-end test against local fixture git repos (no network).
- `uvx skill-dojo==<released version> validate` works in a clean GitHub Actions runner without
  the web extra.
- **Adopt the jenreh repo:** `skill-dojo init --adopt` registers the existing plugins as
  `local` items (with parts where the upstream origin is known), adds
  `registry/`, pins the context7 MCP server, and turns on the symlink layout options.
  Then `scripts/` is deleted and Taskfile and workflows call `skill-dojo`. Afterwards,
  `skill-dojo build && git diff` shows only the intended metadata additions, and
  `skill-dojo validate` passes. Codex and Claude Code still install every plugin.
