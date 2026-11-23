"""Sources: upstream sources, their cached plugins, mirror or pick parts."""

from typing import Any

import reflex as rx
from reflex.event import EventSpec

import skill_dojo_core as core
from skill_dojo_core import SourceType
from skill_dojo_web.state import AppState, off_loop

DETECT = "detect"
NEW = "__new__"
PART_LABEL = {"skill": "skill", "agent": "agent", "mcp_server": "MCP", "hook": "hook"}
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
    version: str = ""
    plugins: list[dict[str, Any]] = []
    query: str = ""
    kind: str = "all"
    adding: bool = False
    new_id: str = ""
    new_repo: str = ""
    new_type: str = DETECT
    cached: bool = False
    expanded: str = ""
    part_rows: list[dict[str, Any]] = []
    local_plugins: list[str] = []
    owners: dict[str, str] = {}
    targets: dict[str, str] = {}
    pending: str = ""
    dialog: bool = False
    target_name: str = ""
    removing: bool = False

    @rx.var
    def target_options(self) -> list[dict[str, str]]:
        return [
            {"value": NEW, "label": "New plugin…"},
            *({"value": p, "label": p} for p in self.local_plugins),
        ]

    @rx.var
    def part_list(self) -> list[dict[str, Any]]:
        """The parts with their switch (in a local plugin?) and own select value."""
        return [
            {
                **r,
                "on": r["spec"] in self.owners,
                "target": self.owners.get(r["spec"])
                or self.targets.get(r["spec"], NEW),
            }
            for r in self.part_rows
        ]

    @rx.var
    def pending_name(self) -> str:
        return self.pending.rsplit("/", 1)[-1]

    @rx.var
    def cannot_create(self) -> bool:
        return not self.target_name.strip()

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
    @off_loop
    def load(self) -> list[EventSpec]:
        return self._load()

    def _load(self) -> list[EventSpec]:
        self.load_shell()
        try:
            listed = core.source_list(self._ctx()).sources
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return self._flush()
        self.sources = [
            {
                "id": s.id,
                "kind": s.type.value,
                "type": TYPE_LABEL[s.type.value],
                "repository": s.repository,
                "url": core.web_url(s.repository),
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
        return self._flush()

    def _browse(self, source_id: str, refresh: bool = False) -> None:
        if source_id != self.selected:
            self.expanded, self.part_rows = "", []
        self.selected = source_id
        try:
            result = core.browse(self._ctx(), source_id, refresh=refresh)
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self.plugins = []
            self._fail(exc)
            return
        self.commit = result.commit[:7]
        self.version = result.version or ""
        self.cached = result.cached
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
                "indexed": p.name in result.parts,
            }
            for p in result.plugins
        ]

    @rx.event
    @off_loop
    def select(self, source_id: str) -> list[EventSpec]:
        self._browse(source_id)
        return self._flush()

    @rx.event
    @off_loop
    def refresh(self) -> list[EventSpec]:
        self._browse(self.selected, refresh=True)
        return self._flush()

    @rx.event
    @off_loop
    def expand(self, plugin: str) -> list[EventSpec]:
        """Show (or hide) the skills, agents, MCP servers and hooks of a plugin."""
        if self.expanded == plugin:
            self.expanded, self.part_rows = "", []
            return []
        try:
            found = core.plugin_parts(self._ctx(), self.selected, plugin).parts
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return self._flush()
        self.expanded = plugin
        self.part_rows = [
            {
                "spec": p.spec,
                "name": p.name,
                "kind": PART_LABEL.get(p.kind, p.kind),
                "description": p.description,
                "version": p.version or "",
            }
            for p in found
        ]
        self._load_owners()
        return self._flush()

    def _load_owners(self) -> None:
        """Which local plugin holds each part (by ``source:plugin/kind/name``)."""
        try:
            overview = core.plugins_overview(self._ctx())
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        self.local_plugins = overview.local
        self.owners = {
            part.spec: p.id
            for p in overview.plugins
            if p.id in overview.local
            for part in p.parts
        }

    def _changed(self) -> None:
        self._load_owners()
        self._browse(self.selected)

    @rx.event
    def set_part_target(self, spec: str, value: str) -> None:
        self.targets = {**self.targets, spec: value or NEW}

    @rx.event
    @off_loop
    def toggle_part(self, spec: str, on: bool) -> list[EventSpec]:
        """On: add the part to its selected plugin (or a new one); off: remove it."""
        owner = self.owners.get(spec)
        if on == bool(owner):
            return []
        part = "/".join(spec.rsplit("/", 2)[1:])
        if owner:
            try:
                core.remove_parts(self._ctx(), owner, [part])
                self._say(f"Removed {part} from {owner}")
                self.targets = {**self.targets, spec: owner}
            except Exception as exc:  # noqa: BLE001 (shown in the UI)
                self._fail(exc)
            self._changed()
            return self._flush()
        target = next(r["target"] for r in self.part_list if r["spec"] == spec)
        if target == NEW:
            self.pending, self.dialog = spec, True
            return []
        try:
            core.add_parts(self._ctx(), target, [spec])
            self._say(f"Added {part} to {target}")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self._changed()
        return self._flush()

    @rx.event
    def close_dialog(self) -> None:
        self.dialog, self.pending = False, ""

    @rx.event
    def set_target_name(self, value: str) -> None:
        self.target_name = value

    @rx.event
    @off_loop
    def create_plugin(self) -> list[EventSpec]:
        """Create the named plugin with the part whose switch was turned on."""
        name = self.target_name.strip()
        try:
            result = core.add_parts(self._ctx(), name, [self.pending], create=True)
            self._say(f"{result.item}: {result.status} with {self.pending_name}")
            self.targets = {**self.targets, self.pending: name}
            self.target_name = ""
            self.dialog, self.pending = False, ""
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self._changed()
        return self._flush()

    @rx.event
    def set_query(self, value: str) -> None:
        self.query = value

    @rx.event
    def set_kind(self, value: str) -> None:
        self.kind = value

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
    @off_loop
    def add_source(self) -> list[EventSpec]:
        try:
            core.source_add(
                self._ctx(),
                self.new_id.strip(),
                self.new_repo.strip(),
                kind=None if self.new_type == DETECT else SourceType(self.new_type),
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
        return self._load()

    @rx.event
    @off_loop
    def set_type(self, value: str) -> list[EventSpec]:
        """Change the selected source's type (``detect``: read it again)."""
        kind = None if value == DETECT else SourceType(value)
        try:
            result = core.source_set_type(self._ctx(), self.selected, kind)
            found = next(s for s in result.sources if s.id == self.selected)
            self._say(f"'{self.selected}' is now {TYPE_LABEL[found.type.value]}")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        return self._load()

    @rx.event
    def ask_remove(self) -> None:
        self.removing = True

    @rx.event
    def close_remove(self) -> None:
        self.removing = False

    @rx.event
    @off_loop
    def remove_source(self) -> list[EventSpec]:
        """Remove the selected source (refused while a plugin still uses it)."""
        self.removing = False
        try:
            core.source_remove(self._ctx(), self.selected)
            self._say(f"Removed source '{self.selected}'")
            self.selected = ""
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        return self._load()

    @rx.event
    @off_loop
    def mirror(self, plugin: str) -> list[EventSpec]:
        try:
            result = core.mirror(self._ctx(), self.selected, plugin)
            self._say(f"{result.item}: {result.status} on the work branch")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self._browse(self.selected)
        return self._flush()

    @rx.event
    @off_loop
    def allow(self, plugin: str) -> list[EventSpec]:
        try:
            core.source_allow(self._ctx(), self.selected, plugin)
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        return self._load()
