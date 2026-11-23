"""The official MCP Registry as a source (API ``/v0.1``).

A server is pinned before it is used: an npm or PyPI package to its exact
version, an OCI image to the digest of its manifest. The pin is the item's
upstream ``commit``. The wrapper plugin is generated from the pinned entry: a
``plugin.json`` and a ``.mcp.json`` with one server.

A source whose repository is a git repo offers the one server of its
``server.json``. There a remote server is pinned by the git commit too.
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from skill_dojo_core import builder, jsontext
from skill_dojo_core.errors import InvalidInputError, NotFoundError, RegistryError
from skill_dojo_core.models import ITEM_ID_RE, SERVER_NAME_RE
from skill_dojo_core.sources import UpstreamPlugin

log = logging.getLogger(__name__)

API = "v0.1"
OFFICIAL = "io.modelcontextprotocol.registry/official"
NPM_RE = re.compile(r"^(?:@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9][a-z0-9._~-]*$")
PYPI_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
VERSION_RE = re.compile(r"^\d+(?:\.\d+)*(?:[.+-]?[0-9A-Za-z][0-9A-Za-z.+_-]*)?$")
OCI_RE = re.compile(
    r"^(?:(?P<host>[a-z0-9.-]+(?::\d+)?)/)?"
    r"(?P<repo>[a-z0-9]+(?:[._/-][a-z0-9]+)*)"
    r"(?::(?P<tag>[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}))?"
    r"(?:@(?P<digest>sha256:[0-9a-f]{64}))?$"
)
WILDCARD_RE = re.compile(r"(?:^|\.)[xX*](?:\.|$)")
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
HEADER_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")
VARIABLE_RE = re.compile(r"(?<!\$)\{([A-Za-z_][A-Za-z0-9_]*)\}")
SERVER_FILE = "server.json"
# server.json remote type -> .mcp.json server type
REMOTE_TYPES = {"streamable-http": "http", "sse": "sse"}
NPM_REGISTRY = "https://registry.npmjs.org"
PYPI_REGISTRY = "https://pypi.org"
DOCKER_HUB = "docker.io"
DOCKER_API = "registry-1.docker.io"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
MANIFEST_TYPES = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)
# registry type -> (command, leading args) that runs the pinned package
RUNNERS: dict[str, tuple[str, list[str]]] = {
    "npm": ("npx", ["-y"]),
    "pypi": ("uvx", []),
    "oci": ("docker", ["run", "-i", "--rm"]),
}
TIMEOUT = 30.0
MAX_PAGES = 20
PAGE_SIZE = 100
UNAUTHORIZED = 401


# --- the registry's data -----------------------------------------------------------


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Argument(ApiModel):
    type: str = "positional"
    name: str | None = None
    value: str | None = None
    value_hint: str | None = Field(default=None, alias="valueHint")
    is_required: bool = Field(default=False, alias="isRequired")


class EnvironmentVariable(ApiModel):
    name: str
    description: str | None = None
    is_required: bool = Field(default=False, alias="isRequired")
    is_secret: bool = Field(default=False, alias="isSecret")


class Transport(ApiModel):
    type: str


class Header(ApiModel):
    name: str
    value: str | None = None
    is_required: bool = Field(default=False, alias="isRequired")


class Remote(ApiModel):
    type: str
    url: str
    headers: list[Header] = Field(default_factory=list)


class Package(ApiModel):
    registry_type: str = Field(alias="registryType")
    registry_base_url: str | None = Field(default=None, alias="registryBaseUrl")
    identifier: str
    version: str | None = None
    transport: Transport
    package_arguments: list[Argument] = Field(
        default_factory=list, alias="packageArguments"
    )
    environment_variables: list[EnvironmentVariable] = Field(
        default_factory=list, alias="environmentVariables"
    )


class ServerEntry(ApiModel):
    """One version of one server, with the registry's status."""

    name: str
    version: str
    description: str = ""
    title: str | None = None
    website_url: str | None = Field(default=None, alias="websiteUrl")
    repository: dict[str, Any] | None = None
    packages: list[Package] = Field(default_factory=list)
    remotes: list[Remote] = Field(default_factory=list)
    status: str = "active"


def _official(data: dict[str, Any]) -> dict[str, Any]:
    """The registry's own ``_meta`` of a response entry."""
    meta = data.get("_meta")
    official = meta.get(OFFICIAL) if isinstance(meta, dict) else None
    return official if isinstance(official, dict) else {}


def _entry(data: Any) -> ServerEntry:
    if not isinstance(data, dict) or not isinstance(data.get("server"), dict):
        raise RegistryError("MCP Registry: response has no 'server'")
    meta = _official(data)
    try:
        entry = ServerEntry.model_validate(data["server"])
    except ValidationError as exc:
        raise RegistryError(f"MCP Registry: bad server entry: {exc}") from exc
    status = meta.get("status")
    return entry.model_copy(update={"status": status or "active"})


# --- HTTP ------------------------------------------------------------------------


def check_url(url: str) -> str:
    """An https URL, or http to this machine (tests, a local mirror)."""
    parts = urlsplit(url)
    local = parts.scheme == "http" and parts.hostname in LOCAL_HOSTS
    if (parts.scheme != "https" and not local) or not parts.hostname:
        raise InvalidInputError(f"'{url}' is not an https URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise InvalidInputError(f"'{url}' must not carry credentials or a query")
    return url.rstrip("/")


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=TIMEOUT,
        follow_redirects=False,
        headers={"User-Agent": "skill-dojo"},
    )


def _get_json(client: httpx.Client, url: str, **params: Any) -> Any:
    try:
        response = client.get(url, params=params or None)
    except httpx.HTTPError as exc:
        raise RegistryError(f"MCP Registry: {exc}") from exc
    if response.status_code == httpx.codes.NOT_FOUND:
        raise NotFoundError(f"MCP Registry: {url} not found")
    if response.status_code != httpx.codes.OK:
        raise RegistryError(f"MCP Registry: HTTP {response.status_code} for {url}")
    try:
        return response.json()
    except ValueError as exc:
        raise RegistryError(f"MCP Registry: {url} did not return JSON") from exc


def list_servers(base_url: str, search: str | None = None) -> list[ServerEntry]:
    """The latest version of every server (matching ``search``)."""
    base = check_url(base_url)
    found: dict[str, ServerEntry] = {}
    cursor: str | None = None
    with _client() as client:
        for _ in range(MAX_PAGES):
            params: dict[str, Any] = {"version": "latest", "limit": PAGE_SIZE}
            if search:
                params["search"] = search
            if cursor:
                params["cursor"] = cursor
            data = _get_json(client, f"{base}/{API}/servers", **params)
            servers = data.get("servers") if isinstance(data, dict) else None
            for item in servers if isinstance(servers, list) else []:
                entry = _entry(item)
                if entry.status != "deleted":
                    found[entry.name] = entry
            metadata = data.get("metadata") or {}
            cursor = metadata.get("nextCursor") if isinstance(metadata, dict) else None
            if not cursor:
                break
        else:
            log.warning("MCP Registry: stopped after %d pages", MAX_PAGES)
    return sorted(found.values(), key=lambda e: e.name)


def get_server(base_url: str, name: str) -> ServerEntry:
    """The latest version of server ``name``; a deleted one is not served."""
    if not SERVER_NAME_RE.match(name) or ".." in name:
        raise InvalidInputError(f"'{name}' is not an MCP server name")
    base = check_url(base_url)
    path = f"servers/{quote(name, safe='')}/versions/latest"
    url = f"{base}/{API}/{path}"
    with _client() as client:
        entry = _entry(_get_json(client, url))
    if entry.name != name:
        raise RegistryError(f"MCP Registry returned '{entry.name}' for '{name}'")
    if entry.status == "deleted":
        raise NotFoundError(f"MCP server '{name}' was deleted from the registry")
    return entry


def offered(
    entry: ServerEntry, repository: str, *, remotes: bool = False
) -> UpstreamPlugin:
    """``entry`` as a plugin a source offers (with why it cannot be pinned)."""
    return UpstreamPlugin(
        name=entry.name,
        path=".",
        repository=repository,
        version=entry.version,
        description=entry.description,
        unsupported=unsupported(entry, remotes=remotes),
    )


# --- server.json in a git repository -------------------------------------------------


def is_repository(url: str) -> bool:
    """A git repo holding a ``server.json`` (GitHub, ``.git``, local), not an API."""
    parts = urlsplit(url)
    if parts.scheme not in {"https", "http"}:
        return True
    host = (parts.hostname or "").removeprefix("www.")
    return host == "github.com" or parts.path.endswith(".git")


def read_server_file(root: Path) -> ServerEntry:
    """The server described by ``server.json`` at the root of a checkout."""
    path = root / SERVER_FILE
    if path.is_symlink() or not path.is_file():
        raise NotFoundError(f"no {SERVER_FILE} at the root of the repository")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entry = ServerEntry.model_validate(data)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise InvalidInputError(f"unreadable {SERVER_FILE}: {exc}") from exc
    if not SERVER_NAME_RE.match(entry.name) or ".." in entry.name:
        raise InvalidInputError(f"'{entry.name}' is not an MCP server name")
    return entry


# --- pinning -------------------------------------------------------------------------


@dataclass(frozen=True)
class Pinned:
    """A package at an exact version or digest."""

    registry_type: str
    identifier: str
    version: str
    reference: str  # what the client runs: pkg@1.2.3, pkg==1.2.3, image@sha256:…

    @property
    def pin(self) -> str:
        """The value recorded as the upstream commit."""
        return f"{self.registry_type}:{self.reference}"


def unsupported(entry: ServerEntry, *, remotes: bool = False) -> str | None:
    """Why ``entry`` cannot be pinned, or ``None``."""
    try:
        choose(entry, remotes=remotes)
    except InvalidInputError as exc:
        return str(exc)
    return None


def choose(entry: ServerEntry, *, remotes: bool = False) -> Package | Remote:
    """The first stdio package we can pin (npm, PyPI, OCI); with ``remotes``
    (a pinned ``server.json``) else the first remote we can use."""
    reasons = []
    candidates = [*entry.packages, *(entry.remotes if remotes else [])]
    for candidate in candidates:
        reason = (
            _package_problem(candidate)
            if isinstance(candidate, Package)
            else _remote_problem(candidate)
        )
        if reason is None:
            return candidate
        reasons.append(reason)
    if not entry.packages and not remotes:
        reasons.append("no package (remote-only servers cannot be pinned)")
    elif not candidates:
        reasons.append("no package and no remote")
    raise InvalidInputError(f"'{entry.name}': " + "; ".join(reasons))


def _remote_problem(remote: Remote) -> str | None:
    if remote.type not in REMOTE_TYPES:
        return f"{remote.type} remotes are not supported"
    parts = urlsplit(remote.url)
    local = parts.scheme == "http" and parts.hostname in LOCAL_HOSTS
    if (parts.scheme != "https" and not local) or not parts.hostname:
        return f"remote '{remote.url}' is not an https URL"
    if parts.username or parts.password:
        return f"remote '{remote.url}' carries credentials"
    if "{" in remote.url:
        return f"remote '{remote.url}' needs URL variables"
    return None


def _package_problem(package: Package) -> str | None:  # noqa: PLR0911
    kind = package.registry_type
    if package.transport.type != "stdio":
        return f"{kind} package uses {package.transport.type}, not stdio"
    if kind == "npm":
        if package.registry_base_url not in {None, NPM_REGISTRY}:
            return "npm package from another registry"
        if not NPM_RE.match(package.identifier):
            return f"'{package.identifier}' is not an npm package name"
        return _version_problem(package.version)
    if kind == "pypi":
        if package.registry_base_url not in {None, PYPI_REGISTRY}:
            return "PyPI package from another index"
        if not PYPI_RE.match(package.identifier):
            return f"'{package.identifier}' is not a PyPI package name"
        return _version_problem(package.version)
    if kind == "oci":
        match = OCI_RE.match(package.identifier)
        if match is None or ".." in package.identifier:
            return f"'{package.identifier}' is not an image reference"
        if not (match["tag"] or match["digest"] or package.version):
            return f"image '{package.identifier}' has no tag or digest"
        return None
    return f"{kind} packages are not supported"


def _version_problem(version: str | None) -> str | None:
    if (
        version is None
        or version == "latest"
        or not VERSION_RE.match(version)
        or WILDCARD_RE.search(version)
    ):
        return f"version '{version}' is not an exact version"
    return None


def pin(package: Package) -> Pinned:
    """Pin ``package``: exact version, or the digest of the image manifest."""
    problem = _package_problem(package)
    if problem is not None:
        raise InvalidInputError(problem)
    kind, name = package.registry_type, package.identifier
    if kind == "npm":
        version = str(package.version)
        return Pinned(kind, name, version, f"{name}@{version}")
    if kind == "pypi":
        version = str(package.version)
        return Pinned(kind, name, version, f"{name}=={version}")
    match = OCI_RE.match(name)
    if match is None:
        raise InvalidInputError(f"'{name}' is not an image reference")
    host = match["host"] or DOCKER_HUB
    repo = match["repo"]
    tag = match["tag"] or package.version or ""
    digest = match["digest"] or resolve_digest(host, repo, tag)
    image = f"{host}/{repo}"
    return Pinned(kind, image, tag or digest, f"{image}@{digest}")


# --- OCI distribution API ----------------------------------------------------------


def _api_base(host: str) -> str:
    if host == DOCKER_HUB:
        return f"https://{DOCKER_API}"
    hostname = urlsplit(f"//{host}").hostname
    return f"{'http' if hostname in LOCAL_HOSTS else 'https'}://{host}"


def _challenge(header: str) -> dict[str, str]:
    """The parameters of a ``WWW-Authenticate: Bearer …`` header."""
    if not header.lower().startswith("bearer "):
        return {}
    return dict(re.findall(r'(\w+)="([^"]*)"', header[len("bearer ") :]))


def _token(client: httpx.Client, header: str) -> str:
    params = _challenge(header)
    realm = params.pop("realm", "")
    if not realm:
        raise RegistryError("container registry asked for an unknown login")
    data = _get_json(client, check_url(realm), **params)
    token = (
        (data.get("token") or data.get("access_token"))
        if isinstance(data, dict)
        else None
    )
    if not isinstance(token, str):
        raise RegistryError("container registry gave no token")
    return token


def resolve_digest(host: str, repo: str, tag: str) -> str:
    """``sha256:…`` of the manifest ``repo:tag`` points at (anonymous pull)."""
    if host == DOCKER_HUB and "/" not in repo:
        repo = f"library/{repo}"
    url = f"{_api_base(host)}/v2/{repo}/manifests/{tag}"
    headers = {"Accept": MANIFEST_TYPES}
    with _client() as client:
        try:
            response = client.get(url, headers=headers)
            if response.status_code == UNAUTHORIZED:
                auth = response.headers.get("www-authenticate", "")
                headers["Authorization"] = f"Bearer {_token(client, auth)}"
                response = client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise RegistryError(f"container registry: {exc}") from exc
    if response.status_code != httpx.codes.OK:
        raise RegistryError(
            f"container registry: HTTP {response.status_code} for {repo}:{tag}"
        )
    digest = f"sha256:{hashlib.sha256(response.content).hexdigest()}"
    claimed = response.headers.get("docker-content-digest")
    if claimed and claimed != digest:
        raise RegistryError(f"manifest of {repo}:{tag} does not match its digest")
    log.debug("Pinned %s:%s to %s", repo, tag, digest)
    return digest


# --- the wrapper plugin --------------------------------------------------------------


def default_item_id(name: str) -> str:
    """``io.github.acme/Weather-MCP`` -> ``weather-mcp``."""
    slug = re.sub(r"[^a-z0-9-]+", "-", name.rsplit("/", 1)[-1].lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")[:64].strip("-")
    if not ITEM_ID_RE.match(slug):
        raise InvalidInputError(f"no plugin name in '{name}'; pass one with --as")
    return slug


def server_key(name: str) -> str:
    """The ``mcpServers`` key of a server: the last part of its name."""
    return name.rsplit("/", 1)[-1]


def _placeholder(text: str) -> str:
    return "${" + (re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_") or "VALUE") + "}"


def _arguments(arguments: list[Argument]) -> list[str]:
    out: list[str] = []
    for arg in arguments:
        value = arg.value
        if value is None and arg.is_required:
            value = _placeholder(arg.value_hint or arg.name or "value")
        if arg.type == "named" and arg.name:
            if value is None:
                continue
            out += [arg.name, value]
        elif value is not None:
            out.append(value)
    return out


def server_config(package: Package, pinned: Pinned) -> dict[str, Any]:
    """The ``mcpServers`` entry that runs the pinned package.

    The registry's ``runtimeArguments`` are never used: placed before the
    pinned reference they could point the runner at another package, image or
    registry. Package arguments come after it and only reach the server.
    """
    env_names = [
        v.name for v in package.environment_variables if ENV_NAME_RE.match(v.name)
    ]
    args = _arguments(package.package_arguments)
    command, lead = RUNNERS[pinned.registry_type]
    if pinned.registry_type == "oci":
        lead = [*lead, *(flag for name in env_names for flag in ("-e", name))]
    config: dict[str, Any] = {
        "type": "stdio",
        "command": command,
        "args": [*lead, pinned.reference, *args],
    }
    if env_names:
        config["env"] = {name: "${" + name + "}" for name in env_names}
    return config


def remote_config(remote: Remote) -> dict[str, Any]:
    """The ``mcpServers`` entry of a remote; header ``{variables}`` and required
    headers without a value become ``${VARIABLES}`` the user sets."""
    config: dict[str, Any] = {"type": REMOTE_TYPES[remote.type], "url": remote.url}
    headers = {}
    for header in remote.headers:
        if not HEADER_RE.match(header.name):
            continue
        value = header.value
        if value is None:
            if not header.is_required:
                continue
            value = _placeholder(header.name)
        headers[header.name] = VARIABLE_RE.sub(lambda m: _placeholder(m[1]), value)
    if headers:
        config["headers"] = headers
    return config


def wrapper_files(
    item_id: str, entry: ServerEntry, server: dict[str, Any]
) -> dict[str, str]:
    """``plugin.json`` and ``.mcp.json`` of the wrapper plugin."""
    manifest: dict[str, Any] = {
        "$schema": builder.PLUGIN_SCHEMA,
        "name": item_id,
        "version": entry.version,
        "description": entry.description or entry.title or entry.name,
    }
    homepage = entry.website_url or (entry.repository or {}).get("url")
    if isinstance(homepage, str) and homepage.startswith("https://"):
        manifest["homepage"] = homepage
    servers = {server_key(entry.name): server}
    return {
        "plugin.json": jsontext.dump(manifest),
        ".mcp.json": jsontext.dump({"mcpServers": servers}),
    }
