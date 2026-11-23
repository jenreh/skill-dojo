# skill-dojo-web

Part of [skill-dojo](https://github.com/jenreh/skill-dojo).

The local web UI: `skill-dojo serve` builds the Reflex app into
`$XDG_CACHE_HOME/skill-dojo/web` (default `~/.cache/skill-dojo/web`) and serves it on
`127.0.0.1` only. Pages: review queue, sources and browse, bundles, marketplace
preview, releases, revoke, audit. The UI is built only from
appkit-mantine components; the design prototype's palette lives in the Mantine
theme (`theme.py`). Each page is a package `pages/<name>/` with `page.py`,
`state.py` and `components/`; shared parts are `state.py` and `components/`. Fonts (Inter, Jost, JetBrains
Mono, SIL OFL 1.1) are bundled, so the UI loads nothing from the internet.

For development, `task run` starts `skill-dojo serve --reload` (Reflex dev mode, hot
reload on changes in `src/skill_dojo_web`, backend on port + 1). Pick a repo with
`task run -- --repo ~/Workspace/templates/agent-skills`; `task run:prod` serves the
prod build.
