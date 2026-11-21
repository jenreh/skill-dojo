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
- The dev container only mounts this project.

## Repository baseline

- [ ] Check the GitHub baseline: `scripts/github_publish.py` (or `python scripts/github_harden.py`
      for an existing repo) sets up branch protection with the `02 Security checks` jobs
      required, Dependabot, secret scanning with push protection, a CodeQL merge gate,
      AI Scan and private vulnerability reporting.
