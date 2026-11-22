# Security

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private vulnerability reporting for
this repository, or contact the maintainers directly.

## Secure defaults

- skill-dojo stores no credentials. Locally it uses `gh auth`; in GitHub Actions the
  token comes from Actions secrets. `betterleaks` scans every commit and pull request.
- Dependencies are locked in `uv.lock` and audited by `task audit` and in CI. GitHub
  Actions and pre-commit hooks are pinned to commit SHAs, tool downloads to checksums,
  and Dependabot keeps them current after a 7-day cooldown.
- `git` and `gh` are always run with argument lists, never through a shell.
- The web UI (`skill-dojo serve`) is local only and binds to `127.0.0.1`.
- The approval is the merge of the one work-branch PR into `main`. skill-dojo never
  merges and never pushes to `main`; branch protection with required reviews (and
  "dismiss stale approvals") is the access control.
- The work branch is never force-pushed. When the scheduled sync pushed meanwhile,
  `finish` merges `origin/<work>` entry by entry and stops on a real conflict.
- Commits of upstream content use `--no-verify`, so local git hooks never run on it.
- The upstream cache (`.skill-dojo/cache/`) is only a speed-up: refs are resolved
  against the remote every time, and a cached checkout is reused only when its
  `HEAD` is exactly the pinned commit and its tree is unchanged.
- The dev container only mounts this project.

## Repository baseline

- [ ] Check the GitHub baseline: `scripts/github_publish.py` (or `python scripts/github_harden.py`
      for an existing repo) sets up branch protection with the `02 Security checks` jobs
      required, Dependabot, secret scanning with push protection, a CodeQL merge gate,
      AI Scan and private vulnerability reporting.

## MCP Registry sources

- Registry and container registry calls use https only (plain http only to
  `localhost`), follow no redirects and send no credentials; an OCI pull token is
  the anonymous one the registry hands out.
- Only stdio packages from npmjs.org, pypi.org or an OCI registry are pinned: npm and
  PyPI to an exact version, images to the sha256 of the manifest the tool downloaded
  (checked against `Docker-Content-Digest`). Ranges, `latest`, other package
  registries and remote-only servers are refused.
- Package names, image references and environment variable names are checked before
  they reach `.mcp.json`, so a registry entry cannot inject command-line options.
  Secrets are never copied: environment variables become `${NAME}` placeholders.
- The registry's `runtimeArguments` are dropped: placed before the pinned reference
  they could make `npx`, `uvx` or `docker` run another package, index or image.
  `validate` also reports a runner option that switches the registry or index before
  the package, and checks the digest on the image `docker run` really starts.
