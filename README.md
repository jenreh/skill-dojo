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
