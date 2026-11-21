"""Findings of a validation run. Errors fail; warnings inform."""

from dataclasses import dataclass, field
from typing import Literal

from skill_dojo_core.results import Result


class Finding(Result):
    level: Literal["error", "warning"]
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


class ValidationReport(Result):
    plugins: int = 0
    skills: int = 0
    errors: list[Finding] = []
    warnings: list[Finding] = []

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class Collector:
    findings: list[Finding] = field(default_factory=list)

    def error(self, path: str, message: str) -> None:
        self.findings.append(Finding(level="error", path=path, message=message))

    def warn(self, path: str, message: str) -> None:
        self.findings.append(Finding(level="warning", path=path, message=message))

    def report(self, plugins: int = 0, skills: int = 0) -> ValidationReport:
        return ValidationReport(
            plugins=plugins,
            skills=skills,
            errors=[f for f in self.findings if f.level == "error"],
            warnings=[f for f in self.findings if f.level == "warning"],
        )
