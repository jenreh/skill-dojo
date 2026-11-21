"""Validation of a curated repo: plugins, skills, catalogs and registry."""

from skill_dojo_core.models import ItemKind
from skill_dojo_core.registry import Registry
from skill_dojo_core.validation.plugins import check_plugins
from skill_dojo_core.validation.registry import check_registry, plugin_paths
from skill_dojo_core.validation.report import Collector, Finding, ValidationReport
from skill_dojo_core.validation.skills import check_skills

__all__ = ["Finding", "ValidationReport", "validate_registry"]


def validate_registry(reg: Registry) -> ValidationReport:
    rep = Collector()
    plugins = plugin_paths(reg.repo)
    check_plugins(reg.repo, plugins, reg.config.layout, rep)
    local = frozenset(i.id for i in reg.items.items if i.kind is ItemKind.LOCAL)
    skills = check_skills(reg.repo, plugins, reg.config, rep, local)
    check_registry(reg, rep)
    return rep.report(plugins=len(plugins), skills=skills)
