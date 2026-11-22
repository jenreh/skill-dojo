# Refined prompt: one working branch, auto versions, release after merge

## Task

Rework skill-dojo so that editing a curated registry follows one simple flow (see the
diagram the user gave: add marketplace → cache → show plugins → mirror whole plugin
**or** pick parts into a new/existing own plugin; or add a new plugin, drop files in,
generate metadata → registry updated). All edits go to **one working branch** in the
admin's checkout. When done, skill-dojo (or the admin by hand) opens one PR into `main`.
After the merge, the admin creates a registry release (CLI or UI). Plugin versions are
maintained by skill-dojo: auto patch bump on change, manual override, and a "finish"
screen listing every changed plugin with a major/minor/patch choice. Mirrors keep the
upstream version. The staging/candidate/approval/promote machinery is removed.

## Context (what exists today)

- uv workspace: `components/skill-dojo-core` (all logic), `skill-dojo-cli` (Typer),
  `skill-dojo-web` (Reflex + appkit-mantine). Rules in `CLAUDE.md` §6 and memory
  `skill-dojo-architecture-decisions` (no ports/adapters; core takes `Context`, returns
  pydantic results, raises `errors.*`; writes take `repo_lock`; GitHub Protocol is the
  only test seam, git is real).
- Current flow (to be replaced): `branches.py` builds `candidate/<item>/<sha>` branches in
  throwaway worktrees and PRs them into `staging`; `commands/review.py` approves/merges;
  `commands/promote.py` builds `promote/<date>` staging→main and writes `approvals.yaml`;
  `commands/release.py` tags `marketplace-vYYYY.MM.DD[.N]` and holds `revoke`.
  `models.py`: `ItemKind` (local/mirror/bundle), `Approval`/`ApprovalsFile`,
  `ChannelPolicy.channels` (staging/main), `Item.quarantined`, `Item.supported_channels`.
- Reusable pieces: `candidates.fetch_plugin`, `fetch_server`, `upstream_files`,
  `vendor_into`, `check_representable`, `risk.*` flags, `bundles.pick/parse_part/
  bump_patch/_set_version/_part_lock`, `items.register_local`, `items.lock_refresh`,
  `builder.apply_build`, `builder.manifest_version[_at]`, `release.release_notes`,
  `release.affected`, `branches.remote_start` (incl. the uncommitted config.yaml check),
  `sources.checkout_source`, `commands/overview.py` read models for the web UI.
- Workflows: `workflows.validate_workflow` (branches main+staging, flags job on staging
  PRs) and `sync_workflow` (one candidate PR per moved upstream).
- Uncommitted work in the tree (`serve.py`, `test_serve.py`, `branches.py`): keep it.

## Decisions (made by the user)

1. Drop staging, candidate branches/PRs, per-item review (approve/reject/quarantine
   PR actions), `approvals.yaml`, approval stamps and `promote`. Merging the one PR into
   `main` is the approval; GitHub branch protection does the review.
2. The working branch lives in the **admin's own checkout**.
3. Versions: auto patch bump + manual set + finish screen with major/minor/patch.
   Bumps land in the PR, never as a commit on `main` after the merge.
4. Release is **manual** (`skill-dojo release` and a UI button), no Action.
5. `local` and `bundle` merge into one kind `local` (own plugin: hand-written files plus
   optional mirrored parts). Kinds left: `mirror`, `local`.
6. Revoke becomes a normal change on the working branch. `quarantined` stays only to make
   `sync` skip an item. `clients.yaml` and `affected` stay.

## Requirements

### A. Working branch (core, new module `worktree_branch.py` or rewrite of `branches.py`)

1. Name from `registry/config.yaml` key `work_branch`, default `skill-dojo/changes`.
2. `ensure_work_branch(ctx)` runs at the start of every writing command:
   - Already on the work branch → use it.
   - Otherwise, working tree must be clean (else `ConflictError` naming the dirty files).
     `git fetch origin`; if `origin/<work>` exists and is **not** fully merged into
     `origin/main` → check it out (tracking). If it is merged or missing → create it fresh
     from `origin/main` (delete the stale local branch first). No other branch logic.
   - Never force-push; never rewrite history the admin pushed.
3. Each writing command makes **one commit** on the work branch (`--no-verify`, message
   `skill-dojo: <action> <item>`). Hand edits are committed by `finish` (or by the admin).
4. `sync` (CLI + scheduled workflow) writes upstream updates into the same work branch:
   one commit per moved mirror/part, skips `quarantined` items, idempotent.
5. `finish [--level patch|minor|major per item] [--no-pr]`: runs build + version step,
   commits remaining changes, pushes the branch, opens or updates **one** PR into `main`
   (reuse `branches.open_or_update`). PR body: changed items with old → new version, kind,
   upstream pin, risk flags vs `origin/main` (reuse `risk` + `candidates.file_changes`).
   `--no-pr` only pushes (admin opens the PR by hand).
6. `status`: work branch state (exists, ahead/behind `origin/main`, dirty files, PR
   number/state/URL, changed items with pending versions).

### B. Adding things (diagram paths)

7. **Sources / cache**: `source add` stores the source and caches its catalog and a part
   index (skills, agents, MCP servers, hooks per plugin) under
   `$XDG_CACHE_HOME/skill-dojo/sources/<id>/<commit>`. `browse` reads the cache;
   `browse --refresh` / `source refresh <id>` refetches. MCP Registry sources keep their
   current pinning rules (memory `skill-dojo-mcp-registry-source`).
8. **4a Mirror whole plugin**: `mirror <source> <plugin> [--as id]` vendors the plugin at
   the pinned commit into the work branch (reuse fetch/vendor/lock code, no PR).
9. **4b Parts**: `add-parts <target-plugin> <parts...> [--create] [--description]
   [--category]` where parts use the existing syntax `source:plugin/kind/name`
   (`mcp:<server>/mcp_server/<key>` for the MCP Registry). `kind` ∈ `skill`, `agent`,
   `mcp_server`, **`hook`** (new). Target may be an existing local plugin (also one
   created empty via path C) or a new one (`--create`). `remove-parts <plugin> <kind/name...>`.
   A `hook` part = one event entry from upstream `hooks/hooks.json` (or the manifest's
   `hooks`) plus the script files it references via `${CLAUDE_PLUGIN_ROOT}`; refuse when
   a referenced file is missing or outside the plugin. Merge into the target's
   `hooks/hooks.json`; refuse on duplicate entry.
10. **C New plugin**: `plugin new <name> [--description] [--category]` creates
    `plugins/<name>/` with `.claude-plugin/plugin.json` (version `0.1.0`), registers a
    `local` item and lock entry. The admin then adds files by hand. `build` (= "generate
    plugin and marketplace metadata for new files") detects new skills/agents/hooks/MCP
    files, refreshes the lock of local items (today `lock refresh`), regenerates
    manifests, catalogs and metadata.
11. Migration: loading `items.yaml` accepts `kind: bundle` and treats it as `local`
    (parts kept); `build` rewrites it as `local`. `approvals.yaml` and
    `channel-policy.yaml` `channels`/`reviewers` are ignored on read and removed by
    `build` (risk tiers/data classification stay). Existing repos keep working.

### C. Versions

12. "Changed" = item's lock `treeSha256` (or its file list) differs from `origin/main`, or
    the item is new / removed.
13. Local plugins: if changed and `plugin.json` version equals the version on
    `origin/main`, `build` sets it to the patch bump. If the branch version is already
    higher (manual or previous bump), leave it. New plugins start at `0.1.0`.
14. `version <item> (--patch|--minor|--major|--set X.Y.Z)` sets the target version
    relative to the `origin/main` version (`--set` must be semver and greater). Stored
    only in `plugin.json` on the branch, no extra state file. Version edits refresh the
    lock so drift checks stay clean (mind memory `skill-dojo-lock-and-hash-scheme`).
15. Mirrors: version = upstream `plugin.json` version, never bumped or settable. If
    upstream has none, fall back to rule 13.
16. Core API `pending_versions(ctx) -> list[PendingVersion]` (item, kind, main version,
    branch version, suggested level, editable flag) feeds both `finish` and the UI.

### D. Release (manual)

17. `release` (CLI + UI button): requires `origin/main` to validate and `build --check`
    clean (as today), tags `marketplace-vYYYY.MM.DD[.N]`, writes notes (added, updated
    with old → new version, removed; reuse `release_notes`), and creates a **GitHub
    Release** for the tag through a new `GitHub.create_release` Protocol method (+ fake).
    Refuses when `origin/main` has no change since the last tag.

### E. Removals and simplifications

18. Delete `commands/promote.py`, `commands/review.py`, candidate branch helpers
    (`candidate_branch`, `candidate_item`, `base_branch`/staging lookups, `view`-based
    candidate builds that only served PRs), `Approval`/`ApprovalsFile`, approval stamping
    in `builder`, `Item.supported_channels`, `Channel.BETA` routing. CLI `review`,
    `promote` and `bundle *` commands go; web review page and bundle page go.
19. `revoke <item> [--to TAG]`: on the work branch, removes the item or rolls it back to
    the tag's content and sets `quarantined: true`; reports `affected` clients.
20. `flags` defaults to base `origin/main`. Validate workflow: branches `main` + PRs into
    `main` only; flags job runs on PRs into `main`. Sync workflow: checks out/creates the
    work branch, runs `sync`, then `finish` (pushes + updates the single PR).
    Respect the pin-skew rule in memory `skill-dojo-workflow-pin-skew`.

### F. Web UI (Reflex, appkit-mantine only, page-package layout per memory `skill-dojo-web-ui`)

21. **Sources** page: list sources, add source, per source the cached plugins; each
    plugin row has "Mirror whole plugin" and an expand showing its skills, agents, MCP
    servers and hooks with checkboxes → "Add to plugin" dialog (existing local plugin or
    new name).
22. **Plugins** page (replaces bundles): all items with kind, version, parts; "New
    plugin" form that shows the directory path to put files in and a "Scan for new
    files" button (= build).
23. **Changes** page (replaces review queue): work-branch status, changed plugins table
    from `pending_versions` with major/minor/patch/custom selector (default patch,
    disabled for mirrors showing the upstream version), risk flags, "Finish & open PR"
    button and the PR link/state.
24. **Releases** page: commits on `origin/main` since the last tag, preview notes,
    "Create release" button, past releases. Clients and audit pages stay.
25. States only orchestrate core calls; core read models live in `commands/overview.py`
    (split if it passes 1000 lines).

### G. Spec update (do this first, before code; it is the reference for the tests)

26. Rewrite `spec/2026-11-21-curated-marketplace-design.md` to the new behaviour, keeping
    its structure and plain style. Bump the header to `Date: 2026-11-22 (rev. 2)` with a
    one-line note on what changed. Sections to change:
    - **Goals** 1–5, 8 and the MCP Registry goal: "candidate PR into staging" → change on
      the work branch; "promote" → one PR into `main` + manual release; bundles →
      parts added to an own (`local`) plugin; hooks as a part kind.
    - **Anti-goals / Decided by the user**: unapproved content can only reach `main`
      through the reviewed PR (branch protection); sync writes to the work branch.
    - **Curated repo layout**: drop `approvals.yaml`; `channel-policy.yaml` keeps only
      risk tier / data classification defaults; `config.yaml` gains `work_branch`.
    - **Provenance metadata**: drop `approved-by`, `approved-at`, `approvedVersion`,
      `reviewEvidence`, `supportedChannels` (and the "Channels" call); `kind` is
      `mirror` or `local`; a local plugin may carry `parts`. Version rules from §C.
    - **Domain model**: remove Candidate and Approval; add WorkBranch (the one branch +
      its PR) and PendingVersion; Release = tag + GitHub Release.
    - **Flow**: new diagram matching the user's picture (sources → cache → browse →
      mirror whole plugin | pick parts into new/existing local plugin; or new plugin →
      add files → build) → work branch commits → finish (versions, PR) → merge → manual
      release. Replace the approval, promotion, revocation and rejection paragraphs with
      the work-branch rules (A), version rules (C), revoke/quarantine (E 19).
    - **Risk flags**: computed against `origin/main`, shown in the work-branch PR body
      and on the Changes page.
    - **CLI surface** and **Web UI pages**: the new command set and pages (B, D, F).
    - **Calls made** items 3–5 (bundles, approval, versions) and **Verification**:
      rewritten to the new flow (same scenario as the e2e test below).
27. Update `spec/2026-11-21-curated-marketplace-plan.md`: add **Phase 8: Work-branch
    rework** (goal, steps, definition of done from this prompt) and mark the parts of
    phases 3, 4 and 6 that it replaces (candidate PRs, review, promote, bundles page) as
    superseded, without deleting the history.

## Deliverables

- Core: new/rewritten `branches.py` (work branch), `commands/work.py` (`status`,
  `finish`), `commands/versions.py`, `commands/plugins.py` (new plugin, add/remove parts;
  absorbs reusable bundle code), rewritten `sync.py`, `release.py` (release + revoke on
  work branch), `sources` cache, `hook` part support, model + migration changes,
  `GitHub.create_release`; promote/review removed. Public API in `__init__.py` updated.
- CLI: `status`, `finish`, `plugin new`, `add-parts`, `remove-parts`, `version`,
  `source refresh`, updated `mirror`/`sync`/`release`/`revoke`/`browse --refresh`;
  removed `review`, `promote`, `bundle`.
- Web: Sources, Plugins, Changes, Releases pages per F.
- Tests first: unit tests per new core module; e2e test (bare repos under `tmp_path`,
  fake GitHub) walking the full diagram: add source → browse → mirror whole plugin →
  add parts to a new plugin → `plugin new` + hand-added skill + build → finish (one PR,
  versions bumped, mirror keeps upstream version) → simulate merge → second edit creates
  a fresh work branch → sync reuses the open work branch → release creates tag + GitHub
  Release. Migration test for an old repo with `bundle` items and `approvals.yaml`.
  Replace `test_phase3_candidates.py` / `test_phase4_release.py` accordingly; web state
  tests for the new pages.
- Spec: design and plan documents updated per G (first commit of the work).
- Docs: README command table and "Curated repo files", `docs/index.md` if it lists
  commands.
- Memory: replace `skill-dojo-approval-and-promote-model` with a note on the work-branch
  + version model; update `skill-dojo-web-ui` page list.

## Success criteria

- `task test` green, coverage ≥ 80%; `task lint` clean; no file > 1000 lines;
  `test_architecture.py` still passes (core imports no typer/reflex).
- Only one branch besides `main` is ever created by skill-dojo (`skill-dojo/changes`),
  and at most one open PR exists at a time.
- After `finish`, every changed local plugin has a higher version than on `main`; each
  mirror carries its upstream version; the PR body lists them.
- `skill-dojo release` on merged `main` creates the tag and a GitHub Release (fake
  records it in tests).
- Reflex prod build of the web UI succeeds (`skill-dojo serve` against a fixture repo),
  and the Sources → Changes → Releases flow works by hand in the browser.

## Out of scope

- Automatic release on merge (GitHub Action), a registry-wide semver.
- Per-item approvals, multiple reviewers, release channels (beta/stable).
- Branch protection setup in curated repos.
- Commands or other part kinds beyond skill, agent, mcp_server, hook.
