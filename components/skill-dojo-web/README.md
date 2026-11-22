# skill-dojo-web

Part of [skill-dojo](https://github.com/jenreh/skill-dojo).

The local web UI: `skill-dojo serve` builds the Reflex app into
`$XDG_CACHE_HOME/skill-dojo/web` (default `~/.cache/skill-dojo/web`) and serves it on
`127.0.0.1` only. Pages: review queue, sources and browse, bundles, marketplace
preview, releases, clients and revocation, audit. Fonts (Inter, Jost, JetBrains
Mono, SIL OFL 1.1) are bundled, so the UI loads nothing from the internet.
