"""Bundles: pick parts from any source and open the bundle's candidate PR."""

from typing import Any

import reflex as rx

import skill_dojo_core as core
from skill_dojo_web.state import AppState

NEW = "__new__"
KIND = {"skill": "skill", "agent": "agent", "mcp_server": "mcp"}


def spec(part: dict[str, Any]) -> str:
    """The ``spec`` core put on a part."""
    return part["spec"]


def _part(part: core.PartInfo) -> dict[str, Any]:
    return {**part.model_dump(), "spec": part.spec}


def _bundle(bundle: core.BundleInfo) -> dict[str, Any]:
    return {**bundle.model_dump(), "parts": [_part(p) for p in bundle.parts]}


class BundlesState(AppState):
    bundles: list[dict[str, Any]] = []
    bundle: str = ""
    new_name: str = ""
    category: str = ""
    description: str = ""
    groups: list[dict[str, Any]] = []
    picked: list[str] = []
    query: str = ""

    @rx.var
    def current(self) -> dict[str, Any]:
        return next((b for b in self.bundles if b["id"] == self.bundle), {})

    @rx.var
    def existing(self) -> list[str]:
        return [spec(p) for p in self.current.get("parts", [])]

    @rx.var
    def parts(self) -> list[dict[str, Any]]:
        """Parts the bundle will have: kept ones first, then new picks."""
        known = {spec(p): p for g in self.groups for p in g["parts"]}
        kept = [p for p in self.current.get("parts", []) if spec(p) in self.picked]
        new = [known[s] for s in self.picked if s not in self.existing and s in known]
        return [
            {**p, "kind_label": KIND.get(p["kind"], p["kind"]), "new": p in new}
            for p in kept + new
        ]

    @rx.var
    def dirty(self) -> bool:
        return sorted(self.picked) != sorted(self.existing) or self.bundle == ""

    @rx.var
    def shown_groups(self) -> list[dict[str, Any]]:
        q = self.query.lower()
        return [
            {
                **g,
                "parts": [
                    {**p, "spec": spec(p), "kind_label": KIND.get(p["kind"], p["kind"])}
                    for p in g["parts"]
                    if q in p["name"].lower()
                ],
            }
            for g in self.groups
        ]

    @rx.var
    def next_version(self) -> str:
        current = self.current
        if not current:
            return "0.1.0"
        return f"{current.get('version')} → {current.get('next_version')}"

    @rx.event
    def load(self) -> None:
        self.load_shell()
        try:
            ctx = self._ctx()
            overview = core.bundles_overview(ctx)
            self.bundles = [_bundle(b) for b in overview.bundles]
            local = overview.local
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        wanted = [("local", i) for i in local]
        for b in self.bundles:
            wanted += [(p["source"], p["plugin"]) for p in b["parts"] if p["source"]]
        params = self.router.page.params
        if params.get("source") and params.get("plugin"):
            wanted.append((str(params["source"]), str(params["plugin"])))
        self.groups = []
        for source, plugin in dict.fromkeys(wanted):
            self._load_plugin(source, plugin)
        ids = [b["id"] for b in self.bundles]
        self._choose(self.bundle if self.bundle in ids else (ids[0] if ids else ""))

    def _load_plugin(self, source: str, plugin: str) -> None:
        try:
            found = core.plugin_parts(self._ctx(), source, plugin)
            parts = [_part(p) for p in found.parts]
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        title = (
            f"{source} · this repo · {plugin}"
            if source == "local"
            else f"{source} · {plugin}"
        )
        self.groups = [*self.groups, {"title": title, "parts": parts}]

    def _choose(self, bundle_id: str) -> None:
        self.bundle = bundle_id
        current = next((b for b in self.bundles if b["id"] == bundle_id), {})
        self.picked = [spec(p) for p in current.get("parts", [])]
        self.description = current.get("description", "")
        self.category = current.get("category") or ""

    @rx.var
    def bundle_options(self) -> list[dict[str, str]]:
        new = {"value": NEW, "label": "New bundle"}
        return [
            new,
            *({"value": b["id"], "label": f"plugins/{b['id']}"} for b in self.bundles),
        ]

    @rx.var
    def bundle_value(self) -> str:
        return self.bundle or NEW

    @rx.event
    def choose(self, bundle_id: str) -> None:
        self._choose("" if bundle_id in {NEW, ""} else bundle_id)

    @rx.event
    def toggle(self, part: str) -> None:
        self.picked = (
            [p for p in self.picked if p != part]
            if part in self.picked
            else [*self.picked, part]
        )

    @rx.event
    def set_query(self, value: str) -> None:
        self.query = value

    @rx.event
    def set_new_name(self, value: str) -> None:
        self.new_name = value

    @rx.event
    def set_category(self, value: str) -> None:
        self.category = value

    @rx.event
    def set_description(self, value: str) -> None:
        self.description = value

    @rx.event
    def discard(self) -> None:
        self._choose(self.bundle)

    @rx.event
    def open_pr(self) -> None:
        try:
            ctx = self._ctx()
            if self.bundle == "":
                result = core.bundle_create(
                    ctx,
                    self.new_name.strip(),
                    self.picked,
                    description=self.description or None,
                    category=self.category or None,
                )
            else:
                added = [p for p in self.picked if p not in self.existing]
                removed = [
                    p.split("/", 1)[1] for p in self.existing if p not in self.picked
                ]
                result = None
                if added:
                    result = core.bundle_add(ctx, self.bundle, added)
                if removed:
                    result = core.bundle_remove(ctx, self.bundle, removed)
                if result is None:
                    self._say("Nothing to change")
                    return
            self._say(f"{result.item}: {result.status} candidate PR")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()
