"""Plugins: every item with kind, version and parts; new plugin; build."""

from typing import Any

import reflex as rx

import skill_dojo_core as core
from skill_dojo_web.state import AppState

KIND = {"skill": "skill", "agent": "agent", "mcp_server": "mcp", "hook": "hook"}


def _plugin(info: core.PluginInfo) -> dict[str, Any]:
    return {
        **info.model_dump(),
        "version": info.version or "-",
        "pin": (info.pin or "")[:12],
        "parts": [
            {
                **p.model_dump(),
                "spec": p.spec,
                "short": f"{p.kind}/{p.name}",
                "kind_label": KIND.get(p.kind, p.kind),
                "commit": (p.commit or "")[:12],
            }
            for p in info.parts
        ],
    }


class PluginsState(AppState):
    plugins: list[dict[str, Any]] = []
    query: str = ""
    new_name: str = ""
    new_description: str = ""
    new_category: str = ""
    scanned: list[str] = []

    @rx.var
    def shown(self) -> list[dict[str, Any]]:
        q = self.query.lower()
        return [
            p
            for p in self.plugins
            if not q or q in f"{p['id']} {p['description']}".lower()
        ]

    @rx.var
    def cannot_create(self) -> bool:
        return not self.new_name.strip()

    @rx.var
    def new_path(self) -> str:
        name = self.new_name.strip() or "<name>"
        return f"plugins/{name}/"

    @rx.event
    def load(self) -> None:
        self.load_shell()
        try:
            found = core.plugins_overview(self._ctx()).plugins
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        self.plugins = [_plugin(p) for p in found]

    @rx.event
    def set_query(self, value: str) -> None:
        self.query = value

    @rx.event
    def set_new_name(self, value: str) -> None:
        self.new_name = value

    @rx.event
    def set_new_description(self, value: str) -> None:
        self.new_description = value

    @rx.event
    def set_new_category(self, value: str) -> None:
        self.new_category = value

    @rx.event
    def create(self) -> None:
        name = self.new_name.strip()
        try:
            core.plugin_new(
                self._ctx(),
                name,
                description=self.new_description.strip() or None,
                category=self.new_category.strip() or None,
            )
            self._say(f"Created plugins/{name}/: add files there, then scan")
            self.new_name, self.new_description, self.new_category = "", "", ""
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()

    @rx.event
    def scan(self) -> None:
        """``build``: lock new files, bump versions, regenerate metadata."""
        try:
            self.scanned = core.build(self._ctx()).changed
            self._say(f"Scan: {len(self.scanned)} file(s) updated")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()

    @rx.event
    def remove_part(self, plugin: str, part: str) -> None:
        try:
            core.remove_parts(self._ctx(), plugin, [part])
            self._say(f"Removed {part} from {plugin}")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()
