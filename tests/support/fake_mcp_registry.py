"""A fake MCP Registry (API ``/v0.1``) and OCI registry on a ``pytest-httpserver``.

Tests publish server versions with ``publish``; the fake serves the newest one
as ``latest``. ``images`` holds OCI manifests by ``repo:tag``; their pull needs
an anonymous bearer token, as on Docker Hub.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from pytest_httpserver import HTTPServer
from werkzeug import Request, Response

OFFICIAL = "io.modelcontextprotocol.registry/official"
TOKEN = "anonymous-pull-token"  # noqa: S105 (a fake, public pull token)


def npm(identifier: str, version: str, **extra: Any) -> dict[str, Any]:
    return {
        "registryType": "npm",
        "identifier": identifier,
        "version": version,
        "transport": {"type": "stdio"},
        **extra,
    }


def pypi(identifier: str, version: str, **extra: Any) -> dict[str, Any]:
    return {
        "registryType": "pypi",
        "identifier": identifier,
        "version": version,
        "transport": {"type": "stdio"},
        **extra,
    }


def oci(identifier: str, **extra: Any) -> dict[str, Any]:
    return {
        "registryType": "oci",
        "identifier": identifier,
        "transport": {"type": "stdio"},
        **extra,
    }


@dataclass
class FakeMcpRegistry:
    server: HTTPServer
    versions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    status: dict[tuple[str, str], str] = field(default_factory=dict)
    images: dict[str, bytes] = field(default_factory=dict)
    bad_digest: set[str] = field(default_factory=set)
    requests: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.server.expect_request(re.compile(r"^/.*$")).respond_with_handler(
            self._handle
        )

    @property
    def url(self) -> str:
        return self.server.url_for("").rstrip("/")

    @property
    def host(self) -> str:
        return f"{self.server.host}:{self.server.port}"

    def publish(
        self,
        name: str,
        version: str,
        packages: list[dict[str, Any]] | None = None,
        **extra: Any,
    ) -> None:
        entry = {
            "name": name,
            "description": f"The {name.rsplit('/', 1)[-1]} server.",
            "version": version,
            "packages": packages or [],
            **extra,
        }
        self.versions.setdefault(name, []).append(entry)

    def image(self, repo_tag: str, body: dict[str, Any]) -> str:
        data = json.dumps(body).encode()
        self.images[repo_tag] = data
        return f"sha256:{hashlib.sha256(data).hexdigest()}"

    def _wrap(self, entry: dict[str, Any], latest: bool) -> dict[str, Any]:
        status = self.status.get((entry["name"], entry["version"]), "active")
        meta = {"status": status, "isLatest": latest}
        return {"server": entry, "_meta": {OFFICIAL: meta}}

    def _handle(self, request: Request) -> Response:
        self.requests.append(request.full_path)
        path = request.path
        if path == "/token":
            return _json({"token": TOKEN})
        if path.startswith("/v2/"):
            return self._manifest(request)
        if path == "/v0.1/servers":
            return self._list(request)
        match = re.match(r"^/v0\.1/servers/(.+)/versions/([^/]+)$", path)
        if match is None or match[1] not in self.versions:
            return Response("not found", status=404)
        known = self.versions[match[1]]
        wanted = known[-1] if match[2] == "latest" else None
        wanted = wanted or next((e for e in known if e["version"] == match[2]), None)
        if wanted is None:
            return Response("not found", status=404)
        return _json(self._wrap(wanted, wanted is known[-1]))

    def _list(self, request: Request) -> Response:
        search = request.args.get("search") or ""
        servers = [
            self._wrap(known[-1], True)
            for name, known in sorted(self.versions.items())
            if search in name
        ]
        # Two pages, so callers must follow nextCursor.
        page = int(request.args.get("cursor") or 0)
        chunk = servers[page * 2 : page * 2 + 2]
        more = len(servers) > page * 2 + 2
        metadata = {"count": len(chunk), "nextCursor": str(page + 1) if more else None}
        return _json({"servers": chunk, "metadata": metadata})

    def _manifest(self, request: Request) -> Response:
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            realm = f'Bearer realm="{self.url}/token",service="fake",scope="pull"'
            return Response(status=401, headers={"WWW-Authenticate": realm})
        match = re.match(r"^/v2/(.+)/manifests/([^/]+)$", request.path)
        key = f"{match[1]}:{match[2]}" if match else ""
        if key not in self.images:
            return Response("unknown manifest", status=404)
        body = self.images[key]
        digest = "sha256:" + hashlib.sha256(body).hexdigest()
        if key in self.bad_digest:
            digest = "sha256:" + "0" * 64
        return Response(
            body,
            headers={
                "Content-Type": "application/vnd.oci.image.index.v1+json",
                "Docker-Content-Digest": digest,
            },
        )


def _json(data: Any) -> Response:
    return Response(json.dumps(data), content_type="application/json")
