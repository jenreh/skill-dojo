"""File and tree hashes, normalization of stamped files, and drift detection.

``sha256`` is over the bytes on disk (for a symlink: its target string). Files the
tool stamps (``SKILL.md``, ``plugin.json``) also get ``normalizedSha256``: the hash
after removing the tool's namespaced keys and canonicalizing, so stamping alone is
never drift. ``treeSha256`` is sha256 of the sorted ``<mode> <sha> <path>`` lines,
using the normalized hash where there is one.
"""

import hashlib
import json
import os
import stat
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from skill_dojo_core import frontmatter
from skill_dojo_core.models import FileLock, Namespace

MANIFESTS = frozenset({"plugin.json", ".claude-plugin/plugin.json"})
IGNORED_NAMES = frozenset({".DS_Store", "Thumbs.db", "__pycache__"})


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_mode(path: Path) -> str:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        return "120000"
    return "100755" if info.st_mode & stat.S_IXUSR else "100644"


def raw_bytes(path: Path) -> bytes:
    if path.is_symlink():
        return str(path.readlink()).encode()
    return path.read_bytes()


def is_stampable(rel: str) -> bool:
    return rel in MANIFESTS or PurePosixPath(rel).name == "SKILL.md"


def _canonical(data: Any) -> bytes:
    return json.dumps(
        data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode()


def normalize_skill(text: str, prefix: str) -> bytes | None:
    try:
        data, doc = frontmatter.load(text)
    except ValueError:
        return None
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        kept = {k: v for k, v in metadata.items() if not str(k).startswith(prefix)}
        if kept:
            data["metadata"] = kept
        else:
            del data["metadata"]
    elif "metadata" in data and metadata is None:
        del data["metadata"]
    return _canonical(data) + b"\n---\n" + doc.body.encode()


def normalize_manifest(text: str, key: str) -> bytes | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    extensions = data.get("extensions")
    if isinstance(extensions, dict):
        extensions.pop(key, None)
        if not extensions:
            del data["extensions"]
    return _canonical(data)


def normalized_sha256(rel: str, data: bytes, namespace: Namespace) -> str | None:
    if not is_stampable(rel):
        return None
    try:
        text = data.decode()
    except UnicodeDecodeError:
        return None
    if rel in MANIFESTS:
        normalized = normalize_manifest(text, namespace.plugin)
    else:
        normalized = normalize_skill(text, namespace.skill)
    return sha256_bytes(normalized) if normalized is not None else None


def hash_file(root: Path, rel: str, namespace: Namespace) -> FileLock:
    path = root / rel
    data = raw_bytes(path)
    mode = file_mode(path)
    normalized = None if mode == "120000" else normalized_sha256(rel, data, namespace)
    return FileLock(mode=mode, sha256=sha256_bytes(data), normalized_sha256=normalized)


def _git_files(root: Path) -> list[str] | None:
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],  # noqa: S607
            cwd=root,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    return [p for p in proc.stdout.decode().split("\0") if p]


def list_files(root: Path) -> list[str]:
    """Files under ``root`` (POSIX paths, sorted), honouring ``.gitignore``.

    Symlinks are listed as files and never followed.
    """
    listed = _git_files(root)
    if listed is None:
        listed = []
        for dirpath, dirnames, filenames in os.walk(root):
            base = Path(dirpath)
            dirnames[:] = [d for d in dirnames if d not in IGNORED_NAMES | {".git"}]
            for name in [*filenames, *(d for d in dirnames if (base / d).is_symlink())]:
                listed.append((base / name).relative_to(root).as_posix())
    return sorted(rel for rel in set(listed) if _is_content(root, rel))


def _is_content(root: Path, rel: str) -> bool:
    if set(PurePosixPath(rel).parts) & IGNORED_NAMES:
        return False
    path = root / rel
    return path.is_symlink() or path.is_file()


def hash_tree(
    root: Path, namespace: Namespace, exclude: Iterable[str] = ()
) -> dict[str, FileLock]:
    skip = set(exclude)
    return {
        rel: hash_file(root, rel, namespace)
        for rel in list_files(root)
        if rel not in skip
    }


def tree_sha256(files: dict[str, FileLock]) -> str:
    lines = "".join(
        f"{lock.mode} {lock.normalized_sha256 or lock.sha256} {rel}\n"
        for rel, lock in sorted(files.items())
    )
    return sha256_bytes(lines.encode())


@dataclass(frozen=True)
class Drift:
    path: str
    change: Literal["changed", "missing", "extra"]


def drift(locked: dict[str, FileLock], current: dict[str, FileLock]) -> list[Drift]:
    """Differences between the locked and the current files of an item."""
    found: list[Drift] = []
    for rel, want in sorted(locked.items()):
        have = current.get(rel)
        if have is None:
            found.append(Drift(rel, "missing"))
        elif have.mode != want.mode or not _same_content(want, have):
            found.append(Drift(rel, "changed"))
    found.extend(Drift(rel, "extra") for rel in sorted(set(current) - set(locked)))
    return found


def _same_content(want: FileLock, have: FileLock) -> bool:
    if have.sha256 == want.sha256:
        return True
    return (
        want.normalized_sha256 is not None
        and have.normalized_sha256 == want.normalized_sha256
    )
