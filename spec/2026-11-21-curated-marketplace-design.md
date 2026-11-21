# Curated Agent Plugin Marketplace Tool: Design

Date: 2026-11-21. Status: approved. Next step: the implementation plan.

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
   browse what they offer, and select plugins, skills, agents and MCP servers.
2. Three kinds of items, **all behind the same gate** (decided by the user):
   - **Mirror**: copy one upstream plugin as it is.
   - **Bundle**: build a new plugin out of skills, agents or MCP servers taken from one or
     more upstream plugins. A bundle may also include local parts.
   - **Local**: the team's own skills and plugins (most jenreh plugins). A change to them
     also goes through a candidate PR into `staging`, with risk flags, a `lock.json` entry
     (the content hash, with `upstreamCommit` = the repo's own commit) and the same
     validation. The MCP pinning rule applies too. Today's unpinned
     `npx -y @upstash/context7-mcp` in `jenreh-core/.mcp.json` must be pinned when the
     jenreh repo is adopted. `validate` fails on any folder under `plugins/` that the
     registry does not track.
3. **Pin every item** to an exact upstream commit, with a recorded archive SHA-256.
   Nothing changes until someone approves it.
4. **Keep things in sync through PRs.** A scheduled GitHub Action checks upstream. Each new
   upstream version becomes a *candidate*, never an automatic update. The Action opens a
   PR into `staging` that contains the diff plus **automatic risk flags**.
5. **Releases.** You promote approved changes from `staging` to `main` and create an
   immutable tag (`marketplace-vYYYY.MM.DD[.N]`). Clients import `main` or a pinned tag.
6. **Publish to several clients.** Agent Plugins 1.0 is the canonical format, written to
   `.agents/plugins/marketplace.json` (ChatGPT, Codex, Copilot). From the same source the
   tool also generates the `.claude-plugin/` manifests for Claude Code.
7. **A CLI** manages everything, and `serve` starts a **local web UI** for the same tasks.
8. **Audit and revocation.** Every sync, approval, promotion and revocation can be traced
   in git. A hand-kept list of clients shows who must be warned when something is revoked.

9. **The MCP Registry is a v1 source** (decided by the user). Browse the official MCP
   Registry. A server entry (npm, PyPI or OCI package) is pinned to an exact package
   version or image digest, and the pinned value is recorded as its `upstreamCommit` /
   `sourceDigest`. It becomes a generated wrapper plugin (one `.mcp.json` plus a
   manifest) or a part inside a bundle. Updates are detected by new registry versions and
   go through the same candidate PR.

## Non-goals (v1)

- Locking down developer machines (managed settings, MDM). The tool only curates. Lock-down
  is handled elsewhere.
- A hosted, shared web console with its own login. In v1 the UI is local only.
- Detecting which workspace imported which tag. ChatGPT, Codex and Claude Code don't report
  this, so clients are recorded by hand.
- A full automated security verdict (an LLM or SAST judging the code). v1 gives risk flags
  and humans decide.
- Editing mirrored content by hand (see "Calls made").

## Anti-goals (a failure even if it works)

- **Lock-in.** The curated repo must stay plain, standard files: valid Agent Plugins and
  Claude manifests, readable YAML, normal git history. Someone must be able to hand-edit it,
  or stop using the tool entirely, and still have a working marketplace. No hidden state, no
  database, no custom format that only this tool can read.
- Unapproved content reaching `main` or a tag through any path.
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
- Sync: a scheduled GitHub Action opens a PR. Merging the PR is the approval.
- A reviewer sees the diff plus risk flags.
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
│   ├── config.yaml           # namespace, pinned skill-dojo version, layout and branding options
│   ├── sources.yaml          # upstream sources, refs, allow-lists, schedule
│   ├── items.yaml            # what is mirrored/bundled, from where, pinned at what
│   ├── approvals.yaml        # approval records (reviewer, PR, policy result, time)
│   ├── channel-policy.yaml   # rules for staging and stable
│   ├── clients.yaml          # hand-kept: workspace or client -> ref/tag in use
│   └── lock.json             # provenance: upstream repo, commit, path, sha256 per file/archive
└── .github/workflows/
    ├── validate-marketplace.yml
    └── sync-upstream.yml
```

Every `registry/` file is readable and editable by hand. The tool rebuilds both
marketplace catalogs from `plugins/` and `registry/`, so a hand edit followed by
`<tool> build` gives a consistent result.

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

Every vendored skill and plugin carries its own origin, license and approval facts inside
its standard files. Then the facts travel with the content even when someone copies a
folder out of the repo, and they are readable without the tool (anti-lock-in).

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
  acme.registry/approved-by: jens
  acme.registry/approved-at: 2026-11-21T10:00:00Z
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
    "approvedBy": "jens",
    "approvedAt": "2026-11-21T10:00:00Z",
    "riskTier": "standard",
    "dataClassification": "internal",
    "reviewEvidence": "https://github.com/<org>/<repo>/pull/123",
    "supportedChannels": ["stable", "internal"]
  },
  "com.openai": { "...": "existing client extensions are kept untouched" }
}
```

**Field set (decided by the user).** The same facts are used in both places: camelCase
under `extensions.<ns>`, and kebab-case string keys under the skill `metadata` prefix.

| Field | Purpose |
|---|---|
| `registryId` | Stable internal identity, e.g. `acme:github-pr-reviewer` |
| `kind` | `mirror`, `bundle` or `local` |
| `upstreamMarketplace` | Original source marketplace, repository or MCP Registry |
| `upstreamPlugin` | Original plugin, skill or server identifier |
| `upstreamRef` | Upstream tag, release or branch that was tracked |
| `upstreamCommit` | Exact source revision (or package version / image digest for MCP Registry) |
| `upstreamVersion`, `upstreamLicense` | As declared upstream |
| `sourceDigest` | SHA-256 of the vendored plugin or skill content |
| `approvedVersion` | The version approved for a channel |
| `approvedBy` / `approvedAt` | Human approval evidence |
| `riskTier` | `low`, `standard`, `restricted` or `forbidden` |
| `dataClassification` | `public`, `internal`, `confidential` (list configurable) |
| `allowedTools` | Explicit tool and network permissions |
| `reviewEvidence` | Link to the candidate PR, scan results or approval ticket |
| `supportedChannels` | Channels the item may be published in (`dev`, `beta`, `stable`, `lts`) |
| `deprecation` | Replacement and removal date, when it applies |

In skill `metadata`, list values (`allowed-tools`, `supported-channels`) are
comma-separated strings, and `deprecation` is two keys (`deprecation-replacement`,
`deprecation-removal-date`), because values must be strings. The portable set lives in
the files. The full record lives in the registry, as described below.

**Where to store what.** The paste says "registry database". Here that is the repo
itself, because there is no database:

| Data | In the plugin or skill folder | In the registry (this repo) |
|---|---|---|
| Identity, source, version, approval status | Yes, the field set above | `items.yaml`, `lock.json`, `approvals.yaml` |
| Full review history, reviewer comments | No | The candidate and promote PRs (their reviews and comments) |
| Scan reports, risk-flag output, large fixtures | No | PR comment plus GitHub Actions artifact, linked from `reviewEvidence` |
| Secrets, API keys, tenant config | Never | Never in the repo: GitHub Actions secrets or local env |
| Org policy, channel promotion rules | No | `registry/channel-policy.yaml` |
| Installation state per workspace | No | `registry/clients.yaml` (hand-kept) |

**Policy effects.** `riskTier: forbidden` blocks promotion. `restricted` needs the number
of reviewers set in `channel-policy.yaml`. An item can only be promoted into a channel
listed in its `supportedChannels`. A changed `allowedTools`, or an upstream metadata
change on its own, is a risk flag and makes a new candidate.

**Channels (my call).** v1 has two channels as branches: `staging` (= `beta`) and `main`
(= `stable`). `dev` and `lts` are allowed values but have no branch in v1. `lts` can come
later as a long-lived tag series.

For a **bundle**, the plugin extension has `"kind": "bundle"` and a `parts` array. It has
one entry per included skill, agent or MCP server, each with its own upstream marketplace,
plugin, path, commit and license. Each included skill also carries its own `metadata` as
above.

Rules:
- **Namespace is configurable per curated repo** (`registry/channel-policy.yaml` or a
  `registry/config.yaml`), for example `acme.registry/` for skills and `com.acme.registry`
  for plugins. Default is derived from the marketplace name.
- **Merge, never replace.** Upstream frontmatter, upstream `metadata` keys and other
  `extensions` (for example `com.openai`) are kept as they are. The tool only adds or
  overwrites keys in its own namespace.
- **Licenses.** The upstream `license` value is copied, and any upstream LICENSE or NOTICE
  file is vendored into the plugin (`licenses/`, as the jenreh repo already does). A
  missing upstream license, or one that changed, is a risk flag.
- **When fields are written.** Upstream fields (`source-*`, `upstream*`, license) are
  written in the candidate PR, so the reviewer sees them. Approval fields (`approved-by`,
  `approved-at`, `reviewEvidence`) are stamped by the promote PR from the merged
  candidate PR's reviews (see Flow). `riskTier` and `dataClassification` are set by the reviewer
  during review (defaults from `channel-policy.yaml`).
- **Drift and hashes.** `lock.json` keeps the upstream content hashes. Hashing and drift
  checks normalize away the tool's own namespaced keys, so stamping metadata is not
  reported as drift, while any other change to a mirrored file is.
- `lock.json` is the full machine record (per-file hashes, archive SHA-256). The in-file
  metadata is the human-readable copy that travels with the content. `validate` checks
  that the two agree.

## Domain model

| Object | Lives in | Purpose |
|---|---|---|
| Source | `sources.yaml` | An upstream marketplace, git repo or MCP Registry |
| Item | `items.yaml` | A mirror (one upstream plugin), a bundle (a new plugin made of picked parts) or a local plugin, each with its refs |
| Candidate | open PR into `staging` + its branch | A discovered upstream version that is not yet approved |
| Approval | `approvals.yaml` + the merged PR | Reviewer, PR, risk flag result, time |
| Release | `lock.json` entry at `main` | An approved, immutable item version |
| MarketplaceRelease | git tag on `main` | A tagged state of the catalogs and the plugin tree |
| Client | `clients.yaml` | Who uses which ref or tag (hand-kept) |
| AuditEvent | git history (commits, PRs, tags) | Derived, never stored separately |

## Flow

```
add source ─► discover (read upstream catalog) ─► select (mirror | bundle)
   ─► resolve ref to commit ─► fetch at commit ─► normalize to Agent Plugins
   ─► validate + risk-flag ─► branch + PR into staging (candidate)
   ─► review: approve (UI or GitHub) ─► merge, write approvals.yaml + lock.json
   ─► promote staging→main ─► build both catalogs ─► validate ─► tag release
```

- The **first import** of an item and every **upstream update** use the same
  candidate-PR path. The scheduled `sync-upstream.yml` runs the "resolve → PR" part for all
  items. The CLI can run it on demand.
- **Approving in the UI** does the same as approving on GitHub: it submits a GitHub PR
  review and merges through `gh`. If branch protection requires a second reviewer, the UI
  shows the PR as waiting and does not get around the rule.
- **Where approval facts come from (my call).** The candidate PR already contains
  everything except the approval: the vendored files, the `lock.json` entry and the
  upstream metadata. Merging needs no tool code, so a merge on github.com works the same
  as one from the UI. The approval facts (approving reviewers, time, PR URL) are read
  from the merged PR through the GitHub API. They are written into `approvals.yaml` and
  into the `approved-by` and `approved-at` metadata by the **promote PR**. No bot ever
  pushes past branch protection.
- **Promotion (my call).** `promote` opens a PR from `staging` to `main`. It moves all of
  `staging` at once, with no cherry-picking single items. The promote PR stamps the
  approval metadata, rebuilds both catalogs and runs `validate`. Merging it and then
  running `release` creates the tag. To leave an item out, revert it on `staging` first.
- **Revocation (my call)** goes straight to `main` as a hotfix PR, followed by an
  automatic back-merge PR into `staging`. A revocation must not wait behind unreviewed
  candidates. It removes or rolls back the item, and the UI lists the clients in
  `clients.yaml` that use an affected tag.
- **Rejection or quarantine**: you close the PR. The item stays pinned at its last approved
  commit. A quarantine flag in `items.yaml` stops future candidates until you clear it.

## Risk flags (shown in the PR body and in the UI)

Computed from the diff between the approved and the candidate content, for example:
new or changed executable scripts, hooks, shell commands in commands or skills, new MCP
servers or changes to their `command`/`args`/`env`/URL, new network endpoints, changed
permissions or allowed tools, binary files, symlinks that point outside the plugin, license
changes, a missing or changed upstream license. Each flag points to file and line. Flags
inform the reviewer. They never block on their own. Blocking is the job of the
`channel-policy.yaml` rules and validation.

## CLI surface (sketch, names left to the builder)

`init` (scaffold a curated repo), `source add|list|remove`, `browse <source>`,
`mirror <source> <plugin>`, `bundle create|add|remove`, `local add`, `sync [--item]` (make candidate
PRs), `review list|show|approve|reject|quarantine`, `promote`, `release`, `build`
(regenerate catalogs and layout), `validate`, `clients add|list`, `revoke`,
`vendor` (consumer side, replaces `add-skills.sh`), `init [--adopt]`, `serve` (needs
`skill-dojo[web]`).

## Web UI pages (local, `serve`)

Sources · Browse/Select (mirror or bundle) · Candidates and review queue (diff, risk flags,
approve/reject/quarantine) · Marketplace preview (the exact catalogs and tree that would be
committed) · Releases (promote, tag, release notes) · Clients · Audit (timeline built from
git).

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
2. **Mirrors are never hand-edited.** To change a mirror, you create your own plugin or
   bundle. A hand edit inside a mirrored folder is caught by `validate` as drift against
   `lock.json`.
3. **Bundles copy exact pinned files** of each picked part and get their own version.
   Any part's upstream change creates a candidate PR for the bundle.
4. **Approval = UI and GitHub PR are one thing.** Git is the single source of truth, and
   the audit trail comes from git history.
5. **Version numbers**: a mirror keeps the upstream `version`. A bundle uses semver and gets
   a patch bump whenever a part changes. Release tags are date-based.
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
10. **What `build` generates.** Both marketplace catalogs and the missing per-plugin
    manifests. Per-repo branding (icon, brand color, the `extensions.com.openai`
    interface block, `agents/openai.yaml` stubs) is generated only if
    `registry/config.yaml` asks for it, ported from `codex_metadata.py`. Because the scripts
    go away, `build` must also do what `link-plugins.sh` does today, as **layout options**
    in `registry/config.yaml`: manifest symlinks (`plugin.json` →
    `.claude-plugin/plugin.json`, `mcp.json` → `.mcp.json`) and the flat `skills/<name>`
    symlink view. Default for a new repo: off. The jenreh repo turns them on. The hardcoded
    plugin list and descriptions in `link-plugins.sh` become data that is read from
    `items.yaml` and the manifests.

## Left to the builder

Module layout, CLI command names, the exact `items.yaml`, `lock.json` and
`channel-policy.yaml` schemas, how to fetch upstream (git sparse checkout or tarball API),
how risk flags are detected, the Reflex page design within appkit-mantine, test strategy
(TDD per the jenreh-python skills), and packaging.

## Verification (what "done" looks like)

- `init` a fresh test repo. `source add` two upstreams (one Agent Plugins marketplace, one
  Claude marketplace). `mirror` one plugin and `bundle` two skills from different sources.
  Each opens a candidate PR into `staging` with risk flags.
- Approve in the UI. The PR is merged, and `approvals.yaml` and `lock.json` are updated.
  `promote` and `release` create a tag. Both catalogs validate with the ported validators.
- Push a change upstream (in a fixture repo). The scheduled sync opens an update PR showing
  the diff and the flags.
- Hand-edit `registry/` and a catalog, run `build` and `validate`: the result is consistent.
  Delete the tool: the repo still imports into Codex and Claude Code.
- `source add` the MCP Registry, add one server as a wrapper plugin and one as a bundle
  part, both pinned. A new registry version (from a fixture) opens a candidate PR.
- Change a local skill: it goes through a candidate PR like upstream items. An untracked
  folder under `plugins/` fails `validate`. An item with `riskTier: forbidden`, or a channel
  not in its `supportedChannels`, cannot be promoted.
- Merge a candidate PR on github.com (not through the UI). The next promote PR still
  stamps the correct `approvedBy`/`approvedAt` from that PR's reviews.
- Change a mirrored file by hand: `validate` reports drift. Stamping namespaced metadata
  does not.
- Every vendored `SKILL.md` has string-only, namespaced `metadata` with source and license.
  Every `plugin.json` has `extensions.<namespace>` with upstream, approval and risk fields.
  Upstream frontmatter and other extensions are unchanged. Both pass the Agent Skills and
  Agent Plugins schema checks.
- Unit tests per module. An end-to-end test against local fixture git repos (no network).
- `uvx skill-dojo==<released version> validate` works in a clean GitHub Actions runner without
  the web extra.
- **Adopt the jenreh repo:** `skill-dojo init --adopt` registers the existing plugins as
  `local` items (and as `mirror`/`bundle` parts where the upstream origin is known), adds
  `registry/`, pins the context7 MCP server, and turns on the symlink layout options.
  Then `scripts/` is deleted and Taskfile and workflows call `skill-dojo`. Afterwards,
  `skill-dojo build && git diff` shows only the intended metadata additions, and
  `skill-dojo validate` passes. Codex and Claude Code still install every plugin.
