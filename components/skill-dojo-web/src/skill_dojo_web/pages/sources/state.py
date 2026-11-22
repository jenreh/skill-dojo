"""Sources and browse: upstream sources, what each offers, mirror or bundle."""

from typing import Any

import reflex as rx

import skill_dojo_core as core
from skill_dojo_core import SourceType
from skill_dojo_web.state import AppState

TYPE_LABEL = {
    "agent_plugins_marketplace": "agent plugins",
    "claude_marketplace": "claude",
    "git": "git",
    "mcp_registry": "mcp registry",
}
KINDS = [
    ("all", "All"),
    ("skill", "Skills"),
    ("agent", "Agents"),
    ("MCP", "MCP"),
    ("hook", "Hooks"),
]


class SourcesState(AppState):
    sources: list[dict[str, Any]] = []
    selected: str = ""
    commit: str = ""
    plugins: list[dict[str, Any]] = []
    query: str = ""
    kind: str = "all"
    focus: str = ""
    adding: bool = False
    new_id: str = ""
    new_repo: str = ""
    new_type: str = SourceType.AGENT_PLUGINS_MARKETPLACE.value

    @rx.var
    def source(self) -> dict[str, Any]:
        return next((s for s in self.sources if s["id"] == self.selected), {})

    @rx.var
    def shown(self) -> list[dict[str, Any]]:
        q = self.query.lower()
        return [
            p
            for p in self.plugins
            if (not q or q in f"{p['name']} {p['description']}".lower())
            and (self.kind == "all" or self.kind in p["contents"])
        ]

    @rx.event
    def load(self) -> None:
        self.load_shell()
        try:
            listed = core.source_list(self._ctx()).sources
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        self.sources = [
            {
                "id": s.id,
                "type": TYPE_LABEL[s.type.value],
                "repository": s.repository,
                "where": s.repository.removeprefix("https://")
                if s.type is SourceType.MCP_REGISTRY
                else f"@{s.ref}"
                + (f" · {len(s.allowlist)} allowed" if s.allowlist else ""),
                "path": s.marketplace_path or "",
            }
            for s in listed
        ]
        ids = [s["id"] for s in self.sources]
        if ids:
            self._browse(self.selected if self.selected in ids else ids[0])

    def _browse(self, source_id: str) -> None:
        self.selected, self.focus = source_id, ""
        try:
            result = core.browse(self._ctx(), source_id)
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self.plugins = []
            self._fail(exc)
            return
        self.commit = result.commit[:7]
        self.plugins = [
            {
                "name": p.name,
                "description": p.description or "",
                "version": p.version or "",
                "contents": p.contents or "",
                "license": p.license or "",
                "allowed": p.allowed,
                "unsupported": p.unsupported or "",
                "tracked": result.tracked.get(p.name, ""),
            }
            for p in result.plugins
        ]

    @rx.event
    def select(self, source_id: str) -> None:
        self._browse(source_id)

    @rx.event
    def refresh(self) -> None:
        self._browse(self.selected)

    @rx.event
    def set_query(self, value: str) -> None:
        self.query = value

    @rx.event
    def set_kind(self, value: str) -> None:
        self.kind = value

    @rx.event
    def set_focus(self, value: str) -> None:
        self.focus = value

    @rx.event
    def toggle_add(self) -> None:
        self.adding = not self.adding

    @rx.event
    def set_new_id(self, value: str) -> None:
        self.new_id = value

    @rx.event
    def set_new_repo(self, value: str) -> None:
        self.new_repo = value

    @rx.event
    def set_new_type(self, value: str) -> None:
        self.new_type = value

    @rx.event
    def add_source(self) -> None:
        try:
            core.source_add(
                self._ctx(),
                self.new_id.strip(),
                self.new_repo.strip(),
                kind=SourceType(self.new_type),
            )
            self._say(f"Added source '{self.new_id}'")
            self.selected, self.adding, self.new_id, self.new_repo = (
                self.new_id.strip(),
                False,
                "",
                "",
            )
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()

    @rx.event
    def mirror(self, plugin: str) -> None:
        try:
            result = core.mirror(self._ctx(), self.selected, plugin)
            self._say(f"{result.item}: {result.status} candidate PR")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self._browse(self.selected)

    @rx.event
    def allow(self, plugin: str) -> None:
        try:
            core.source_allow(self._ctx(), self.selected, plugin)
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()
