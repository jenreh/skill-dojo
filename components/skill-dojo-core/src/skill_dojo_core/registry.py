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

from skill_dojo_core import git
from skill_dojo_core.errors import InvalidInputError, NotFoundError
from skill_dojo_core.models import (
    LEGACY_KINDS,
    LEGACY_POLICY_KEYS,
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
# Rev. 1 only: approvals now live in the merged PR; build removes the file.
LEGACY_APPROVALS = "approvals.yaml"
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
    """The key that identifies each entry, when it is there and unique."""
    for key in MATCH_KEYS:
        if items and all(isinstance(i, dict) and key in i for i in items):
            values = [str(i[key]) for i in items]
            return key if len(set(values)) == len(values) else None
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


def yaml_text(
    repo: Path, name: str, model: BaseModel, *, defaults: bool = False
) -> tuple[str, str | None]:
    """(new text, current text or None) of ``registry/<name>`` for ``model``."""
    path = registry_path(repo, name)
    new = _compact(model.model_dump(mode="json"), defaults=defaults)
    before = path.read_text(encoding="utf-8") if path.is_file() else None
    raw = _read_yaml(path) if before is not None else None
    return dump_yaml(merge(raw, new) if raw is not None else new), before


def save_yaml_model(
    repo: Path, name: str, model: BaseModel, *, defaults: bool = False
) -> bool:
    """Write ``model`` into ``registry/<name>``. Returns whether the file changed.

    ``defaults=True`` also writes ``false`` and empty values, so a new file shows
    every option.
    """
    text, before = yaml_text(repo, name, model, defaults=defaults)
    if text == before:
        return False
    path = registry_path(repo, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _legacy_items(raw: Any) -> bool:
    items = raw.get("items") if isinstance(raw, dict) else None
    return isinstance(items, list) and any(
        isinstance(i, dict)
        and (i.get("kind") in LEGACY_KINDS or "supported_channels" in i)
        for i in items
    )


def _legacy_policy(raw: Any) -> bool:
    return isinstance(raw, dict) and bool(LEGACY_POLICY_KEYS & set(raw))


def legacy_files(repo: Path) -> list[str]:
    """The ``registry/`` files that still use the rev. 1 format."""
    found = []
    for name, check in ((ITEMS, _legacy_items), (POLICY, _legacy_policy)):
        path = registry_path(repo, name)
        if path.is_file() and check(_read_yaml(path)):
            found.append(name)
    if registry_path(repo, LEGACY_APPROVALS).is_file():
        found.append(LEGACY_APPROVALS)
    return found


def model_at[M: BaseModel](repo: Path, ref: str, name: str, model: type[M]) -> M:
    """A registry file as it is at ``ref`` (empty model when absent)."""
    data = git.show_file(repo, ref, f"{REGISTRY_DIR}/{name}")
    if data is None:
        return model()
    try:
        if name == LOCK:
            return model.model_validate_json(data)
        raw = yaml_rt().load(data.decode("utf-8"))
        return model.model_validate(_plain(raw) or {})
    except (ValidationError, YAMLError, UnicodeDecodeError) as exc:
        raise InvalidInputError(f"{ref}:{REGISTRY_DIR}/{name}: {exc}") from exc


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
            policy=load_yaml_model(repo, POLICY, ChannelPolicy),
            clients=load_yaml_model(repo, CLIENTS, ClientsFile),
            lock=load_lock(repo),
        )

    def save_items(self) -> bool:
        return save_yaml_model(self.repo, ITEMS, self.items)

    def save_lock(self) -> bool:
        return save_lock(self.repo, self.lock)
