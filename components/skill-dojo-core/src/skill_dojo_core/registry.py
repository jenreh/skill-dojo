"""Load and save the ``registry/`` files of a curated repo.

YAML goes through ruamel round-trip mode: a save merges the model into the
existing document, so comments, key order and hand-added keys survive.
"""

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError

from skill_dojo_core.errors import InvalidInputError, NotFoundError
from skill_dojo_core.models import (
    ApprovalsFile,
    ChannelPolicy,
    ClientsFile,
    ItemsFile,
    LockFile,
    RegistryConfig,
    SourcesFile,
)

REGISTRY_DIR = "registry"
CONFIG = "config.yaml"
SOURCES = "sources.yaml"
ITEMS = "items.yaml"
APPROVALS = "approvals.yaml"
POLICY = "channel-policy.yaml"
CLIENTS = "clients.yaml"
LOCK = "lock.json"
MATCH_KEYS = ("id", "name", "item")


def yaml_rt() -> YAML:
    yaml = YAML()
    yaml.width = 4096
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def registry_path(repo: Path, name: str) -> Path:
    return repo / REGISTRY_DIR / name


def _read_yaml(path: Path) -> Any:
    try:
        return yaml_rt().load(path.read_text(encoding="utf-8"))
    except YAMLError as exc:
        raise InvalidInputError(f"{path}: invalid YAML: {exc}") from exc


def _plain(data: Any) -> Any:
    """ruamel containers -> plain dict/list (for pydantic)."""
    return json.loads(json.dumps(data, default=str))


def load_yaml_model[M: BaseModel](
    repo: Path, name: str, model: type[M], *, required: bool = False
) -> M:
    path = registry_path(repo, name)
    if not path.is_file():
        if required:
            raise NotFoundError(f"{path} not found (run 'skill-dojo init')")
        return model()
    raw = _read_yaml(path)
    try:
        return model.model_validate(_plain(raw) or {})
    except ValidationError as exc:
        raise InvalidInputError(f"{path}: {exc}") from exc


def _compact(data: Any, *, defaults: bool, top: bool = True) -> Any:
    """Drop ``None``; below the top level, unless ``defaults``, also ``[]``/``False``."""
    keep_empty = defaults or top
    if isinstance(data, dict):
        return {
            k: _compact(v, defaults=defaults, top=False)
            for k, v in data.items()
            if v is not None and (keep_empty or (v is not False and v != []))
        }
    if isinstance(data, list):
        return [_compact(v, defaults=defaults, top=False) for v in data]
    return data


def _match_key(items: list[Any]) -> str | None:
    for key in MATCH_KEYS:
        if items and all(isinstance(i, dict) and key in i for i in items):
            return key
    return None


def merge(target: Any, new: Any) -> Any:
    """Merge plain ``new`` into the ruamel node ``target``, keeping comments."""
    if isinstance(target, CommentedMap) and isinstance(new, dict):
        for key in [k for k in target if k not in new]:
            del target[key]
        for key, value in new.items():
            target[key] = merge(target[key], value) if key in target else value
        return target
    if isinstance(target, CommentedSeq) and isinstance(new, list):
        key = _match_key(new)
        if key is None or _match_key(list(target)) != key:
            target[:] = new
            return target
        old = {item[key]: item for item in target}
        merged = [merge(old[v[key]], v) if v[key] in old else v for v in new]
        target[:] = merged
        return target
    return new


def dump_yaml(data: Any) -> str:
    out = io.StringIO()
    yaml_rt().dump(data, out)
    return out.getvalue()


def save_yaml_model(
    repo: Path, name: str, model: BaseModel, *, defaults: bool = False
) -> bool:
    """Write ``model`` into ``registry/<name>``. Returns whether the file changed.

    ``defaults=True`` also writes ``false`` and empty values, so a new file shows
    every option.
    """
    path = registry_path(repo, name)
    new = _compact(model.model_dump(mode="json"), defaults=defaults)
    before = path.read_text(encoding="utf-8") if path.is_file() else None
    raw = _read_yaml(path) if before is not None else None
    text = dump_yaml(merge(raw, new) if raw is not None else new)
    if text == before:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def load_lock(repo: Path) -> LockFile:
    path = registry_path(repo, LOCK)
    if not path.is_file():
        return LockFile()
    try:
        return LockFile.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise InvalidInputError(f"{path}: {exc}") from exc


def render_lock(lock: LockFile) -> str:
    data = lock.model_dump(mode="json", by_alias=True, exclude_none=True)
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def save_lock(repo: Path, lock: LockFile) -> bool:
    path = registry_path(repo, LOCK)
    text = render_lock(lock)
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


@dataclass
class Registry:
    """All registry files of one repo, loaded together."""

    repo: Path
    config: RegistryConfig
    sources: SourcesFile
    items: ItemsFile
    approvals: ApprovalsFile
    policy: ChannelPolicy
    clients: ClientsFile
    lock: LockFile

    @classmethod
    def load(cls, repo: Path) -> Registry:
        return cls(
            repo=repo,
            config=load_yaml_model(repo, CONFIG, RegistryConfig, required=True),
            sources=load_yaml_model(repo, SOURCES, SourcesFile),
            items=load_yaml_model(repo, ITEMS, ItemsFile),
            approvals=load_yaml_model(repo, APPROVALS, ApprovalsFile),
            policy=load_yaml_model(repo, POLICY, ChannelPolicy),
            clients=load_yaml_model(repo, CLIENTS, ClientsFile),
            lock=load_lock(repo),
        )

    def save_items(self) -> bool:
        return save_yaml_model(self.repo, ITEMS, self.items)

    def save_sources(self) -> bool:
        return save_yaml_model(self.repo, SOURCES, self.sources)

    def save_approvals(self) -> bool:
        return save_yaml_model(self.repo, APPROVALS, self.approvals)

    def save_clients(self) -> bool:
        return save_yaml_model(self.repo, CLIENTS, self.clients)

    def save_lock(self) -> bool:
        return save_lock(self.repo, self.lock)
