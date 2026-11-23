"""Pydantic models of the curated repo's ``registry/`` files and ``lock.json``.

YAML files use snake_case keys; ``lock.json`` uses camelCase (it is JSON next to
Agent Plugins manifests). Unknown keys are kept on load so hand edits survive.
"""

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from skill_dojo_core.errors import InvalidInputError

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ITEM_ID_RE = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
DNS_LABEL_RE = re.compile(r"[^a-z0-9-]+")
PART_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
MAX_SERVER_NAME = 200
SERVER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]*/[a-zA-Z0-9][a-zA-Z0-9._-]*$")


class ItemKind(StrEnum):
    LOCAL = "local"
    MIRROR = "mirror"


# Kind names older repos used; ``bundle`` is a local plugin with parts.
LEGACY_KINDS = {"bundle": ItemKind.LOCAL.value}
DEFAULT_WORK_BRANCH = "skill-dojo/changes"
WORK_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def _legacy_kind(value: object) -> object:
    return LEGACY_KINDS.get(value, value) if isinstance(value, str) else value


class RiskTier(StrEnum):
    LOW = "low"
    STANDARD = "standard"
    RESTRICTED = "restricted"
    FORBIDDEN = "forbidden"


class SourceType(StrEnum):
    AGENT_PLUGINS_MARKETPLACE = "agent_plugins_marketplace"
    CLAUDE_MARKETPLACE = "claude_marketplace"
    GIT = "git"
    MCP_REGISTRY = "mcp_registry"


def _item_id(value: str) -> str:
    if not (1 <= len(value) <= 64) or not ITEM_ID_RE.match(value):
        raise ValueError(f"'{value}' is not a valid plugin name")
    return value


ItemId = Annotated[str, AfterValidator(_item_id)]


class YamlModel(BaseModel):
    """Base of the hand-editable YAML models."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid"
    )


def namespace_slug(name: str) -> str:
    """``Acme Tools`` -> ``acme-tools``: a DNS label for the namespace."""
    slug = DNS_LABEL_RE.sub("-", name.lower()).strip("-")
    return slug or "marketplace"


# --- registry/config.yaml ---------------------------------------------------


class Namespace(YamlModel):
    skill: str = Field(
        description="Prefix of SKILL.md metadata keys, e.g. acme.registry/"
    )
    plugin: str = Field(description="plugin.json extension key, e.g. com.acme.registry")

    @field_validator("skill")
    @classmethod
    def _skill_prefix(cls, value: str) -> str:
        if not value.endswith("/") or "/" in value[:-1]:
            raise ValueError("namespace.skill must end with a single '/'")
        return value

    @field_validator("plugin")
    @classmethod
    def _plugin_key(cls, value: str) -> str:
        if not re.match(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+$", value):
            raise ValueError("namespace.plugin must be a reverse-domain key")
        return value

    @classmethod
    def from_name(cls, name: str) -> Namespace:
        slug = namespace_slug(name)
        return cls(skill=f"{slug}.registry/", plugin=f"com.{slug}.registry")


class ToolPin(YamlModel):
    """Exact pin of skill-dojo in the curated repo's workflows."""

    git: str | None = None
    version: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> ToolPin:
        if (self.git is None) == (self.version is None):
            raise ValueError("tool needs exactly one of 'git' or 'version'")
        if self.git is not None and not COMMIT_RE.match(self.git):
            raise ValueError("tool.git must be a 40-character commit SHA")
        if self.version is not None and not re.match(r"^\d+\.\d+\.\d+$", self.version):
            raise ValueError("tool.version must be an exact X.Y.Z version")
        return self


def tool_pin(git: str | None, version: str | None) -> ToolPin:
    """A pin from CLI-style options; exactly one must be given."""
    if (git is None) == (version is None):
        raise InvalidInputError("give exactly one of a git SHA or a version")
    try:
        return ToolPin(git=git, version=version)
    except ValueError as exc:
        raise InvalidInputError(str(exc)) from exc


class Layout(YamlModel):
    manifest_symlinks: bool = False
    mcp_symlink: bool = False
    flat_skills: bool = False


class Branding(YamlModel):
    """Codex / ChatGPT card data, applied to local and bundle plugins only."""

    icon: str | None = Field(default=None, description="Repo path of the icon")
    brand_color: str | None = None
    developer_name: str | None = None
    website_url: str | None = None
    openai_yaml_stubs: bool = True


class Owner(YamlModel):
    name: str
    email: str | None = None
    url: str | None = None


class Policy(YamlModel):
    installation: str = "AVAILABLE"
    authentication: str = "ON_INSTALL"


def _branch_name(value: str) -> str:
    if not WORK_BRANCH_RE.match(value) or ".." in value or value.endswith("/"):
        raise ValueError(f"'{value}' is not a valid branch name")
    return value


BranchName = Annotated[str, AfterValidator(_branch_name)]


class RegistryConfig(YamlModel):
    name: ItemId
    repository: str | None = Field(
        default=None, description="owner/name of this curated repo on GitHub"
    )
    display_name: str | None = None
    description: str | None = None
    owner: Owner | None = None
    namespace: Namespace
    tool: ToolPin
    layout: Layout = Field(default_factory=Layout)
    branding: Branding | None = None
    work_branch: BranchName = DEFAULT_WORK_BRANCH
    main_branch: BranchName = "main"
    default_category: str = "Coding"
    default_policy: Policy = Field(default_factory=Policy)
    categories: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _own_work_branch(self) -> RegistryConfig:
        if self.work_branch == self.main_branch:
            raise ValueError("work_branch must not be the main branch")
        return self


# --- registry/sources.yaml --------------------------------------------------


class Source(YamlModel):
    id: ItemId
    type: SourceType
    repository: str
    marketplace_path: str | None = None
    ref: str = "main"
    allowlist: list[str] = Field(default_factory=list)


class SourcesFile(YamlModel):
    sources: list[Source] = Field(default_factory=list)


# --- registry/items.yaml ----------------------------------------------------


def _part_name(value: str) -> str:
    if not PART_NAME_RE.match(value) or ".." in value:
        raise ValueError(f"'{value}' is not a valid part name")
    return value


def _relative_path(value: str) -> str:
    """A plain relative path: no absolute path, no ``..``, no empty parts."""
    parts = value.split("/")
    if (
        value.startswith("/")
        or "\\" in value
        or any(p in {"", ".", ".."} for p in parts)
    ):
        raise ValueError(f"'{value}' is not a plain relative path")
    return value


RelativePath = Annotated[str, AfterValidator(_relative_path)]


def _plugin_ref(value: str) -> str:
    """A plugin name, or an MCP Registry server name (``io.github.acme/x``)."""
    if (
        SERVER_NAME_RE.match(value)
        and ".." not in value
        and len(value) <= MAX_SERVER_NAME
    ):
        return value
    return _item_id(value)


type PartKind = Literal["skill", "agent", "mcp_server", "hook"]


class Part(YamlModel):
    """One skill, agent, MCP server or hook inside a local plugin."""

    kind: PartKind
    name: Annotated[str, AfterValidator(_part_name)]
    source: ItemId | None = None
    upstream_plugin: Annotated[str, AfterValidator(_plugin_ref)] | None = None
    ref: str | None = None
    commit: str | None = None


class Deprecation(YamlModel):
    replacement: str | None = None
    removal_date: str | None = None


class Item(YamlModel):
    id: ItemId
    kind: ItemKind
    source: str | None = None
    upstream_plugin: str | None = None
    parts: list[Part] = Field(default_factory=list)
    ref: str | None = None
    commit: str | None = None
    quarantined: bool = False
    risk_tier: RiskTier | None = None
    data_classification: str | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    category: str | None = None
    policy: Policy | None = None
    deprecation: Deprecation | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate(cls, data: object) -> object:
        """``kind: bundle`` is ``local``; release channels are gone."""
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k != "supported_channels"}
            if "kind" in data:
                data["kind"] = _legacy_kind(data["kind"])
        return data


class ItemsFile(YamlModel):
    items: list[Item] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> ItemsFile:
        ids = [item.id for item in self.items]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate item ids: {', '.join(dupes)}")
        return self

    def get(self, item_id: str) -> Item | None:
        return next((item for item in self.items if item.id == item_id), None)


# --- registry/channel-policy.yaml -------------------------------------------

LEGACY_POLICY_KEYS = frozenset({"channels", "reviewers"})


class ChannelPolicy(YamlModel):
    """Defaults for risk tier and data classification (``channel-policy.yaml``)."""

    default_risk_tier: RiskTier = RiskTier.STANDARD
    default_data_classification: str = "internal"
    data_classifications: list[str] = Field(
        default_factory=lambda: ["public", "internal", "confidential"]
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate(cls, data: object) -> object:
        """Staging channels and reviewer counts are gone (rev. 2)."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k not in LEGACY_POLICY_KEYS}
        return data


# --- registry/clients.yaml --------------------------------------------------


class Client(YamlModel):
    name: str
    ref: str
    contact: str | None = None
    notes: str | None = None


class ClientsFile(YamlModel):
    clients: list[Client] = Field(default_factory=list)


# --- registry/lock.json -----------------------------------------------------


def _sha256(value: str | None) -> str | None:
    if value is not None and not SHA256_RE.match(value):
        raise ValueError(f"'{value}' is not a sha256 hex digest")
    return value


Sha256 = Annotated[str, AfterValidator(_sha256)]


class FileLock(CamelModel):
    mode: str
    sha256: Sha256
    normalized_sha256: Annotated[str | None, AfterValidator(_sha256)] = None


class Upstream(CamelModel):
    repository: str
    commit: str
    path: str
    ref: str | None = None
    plugin: str | None = None
    license: str | None = Field(
        default=None, description="License the upstream manifest declares"
    )


class PartLock(CamelModel):
    kind: str
    name: str
    path: str
    upstream: Upstream


class ItemLock(CamelModel):
    kind: Annotated[ItemKind, BeforeValidator(_legacy_kind)]
    version: str | None = None
    upstream: Upstream
    parts: list[PartLock] = Field(default_factory=list)
    tree_sha256: Sha256
    files: dict[str, FileLock]
    generated: list[RelativePath] = Field(
        default_factory=list,
        description="Paths build generated (not upstream content, not hashed)",
    )


class LockFile(CamelModel):
    lock_version: Literal[1] = 1
    items: dict[str, ItemLock] = Field(default_factory=dict)
