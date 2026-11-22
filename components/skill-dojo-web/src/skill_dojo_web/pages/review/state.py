"""Review queue: candidate PRs into staging, their flags and diff, the decision."""

from typing import Any

import reflex as rx

import skill_dojo_core as core
from skill_dojo_core import Channel, RiskTier
from skill_dojo_web.state import AppState


class ReviewState(AppState):
    entries: list[dict[str, Any]] = []
    quarantined: list[str] = []
    filter: str = "all"
    selected: int = 0
    detail: dict[str, Any] = {}
    tab: str = "diff"
    tier: str = "standard"
    classification: str = "internal"
    beta: bool = True
    stable: bool = True

    @rx.var
    def rows(self) -> list[dict[str, Any]]:
        if self.filter == "flagged":
            return [e for e in self.entries if e["flags"] > 0]
        if self.filter == "quarantined":
            return []
        return self.entries

    @rx.var
    def flagged_count(self) -> int:
        return sum(1 for e in self.entries if e["flags"] > 0)

    @rx.var
    def flags(self) -> list[dict[str, Any]]:
        return [
            {
                **f,
                "tone": core.flag_severity(f["kind"]),
                "where": f["path"] + (f":{f['line']}" if f.get("line") else ""),
            }
            for f in self.detail.get("flags", [])
        ]

    @rx.var
    def files(self) -> list[dict[str, Any]]:
        return self.detail.get("files", [])

    @rx.var
    def added(self) -> int:
        return sum(f["added"] for f in self.files)

    @rx.var
    def removed(self) -> int:
        return sum(f["removed"] for f in self.files)

    @rx.var
    def approvals(self) -> list[str]:
        return list(self.detail.get("approvals", []))

    @rx.var
    def approved_count(self) -> int:
        return len(self.approvals)

    @rx.var
    def review_percent(self) -> int:
        needed = max(int(self.detail.get("reviewers_needed", 1)), 1)
        return min(100, round(100 * self.approved_count / needed))

    @rx.event
    def load(self) -> None:
        self.load_shell()
        try:
            listed = core.review_list(self._ctx())
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        self.entries = [
            {
                "number": e.pull_request.number,
                "item": e.item or e.pull_request.head,
                "kind": e.kind or "new",
                "title": e.pull_request.title,
                "pin": e.pin,
                "flags": e.flags,
                "age": (e.pull_request.created_at or "")[:10],
            }
            for e in listed.entries
        ]
        self.quarantined = listed.quarantined
        numbers = [e["number"] for e in self.entries]
        if numbers:
            self._open(self.selected if self.selected in numbers else numbers[0])
        else:
            self.selected, self.detail = 0, {}

    def _open(self, number: int) -> None:
        try:
            detail = core.review_detail(self._ctx(), number)
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
            return
        self.selected, self.tab = number, "diff"
        self.detail = detail.model_dump(mode="json")
        self.tier, self.classification = detail.risk_tier, detail.data_classification
        self.beta, self.stable = "beta" in detail.channels, "stable" in detail.channels

    @rx.event
    def select(self, number: int) -> None:
        self._open(number)

    @rx.event
    def set_filter(self, value: str) -> None:
        self.filter = value

    @rx.event
    def set_tab(self, value: str) -> None:
        self.tab = value

    @rx.event
    def set_tier(self, value: str) -> None:
        self.tier = value

    @rx.event
    def set_classification(self, value: str) -> None:
        self.classification = value

    @rx.event
    def set_beta(self, value: bool) -> None:
        self.beta = value

    @rx.event
    def set_stable(self, value: bool) -> None:
        self.stable = value

    @rx.event
    def approve(self) -> None:
        number = self.selected
        channels = [
            c
            for c, on in ((Channel.BETA, self.beta), (Channel.STABLE, self.stable))
            if on
        ]
        try:
            result = core.review_decide(
                self._ctx(),
                number,
                risk_tier=RiskTier(self.tier),
                data_classification=self.classification,
                channels=channels,
            )
            self._say(f"PR #{number}: {result.status}", ok=result.status == "merged")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()

    @rx.event
    def reject(self) -> None:
        self._act(core.review_reject, "rejected")

    @rx.event
    def quarantine(self) -> None:
        self._act(core.review_quarantine, "quarantined")

    def _act(self, action: Any, word: str) -> None:
        try:
            action(self._ctx(), self.selected)
            self._say(f"PR #{self.selected} {word}")
        except Exception as exc:  # noqa: BLE001 (shown in the UI)
            self._fail(exc)
        self.load()
