import pytest

from skill_dojo_core.validation.mcp_pins import floating_reference


@pytest.mark.parametrize(
    ("command", "args"),
    [
        ("npx", ["-y", "@upstash/context7-mcp@2.1.0"]),
        ("npx", ["-y", "pkg@1.0.0", "--flag"]),
        ("npx", ["-p", "tool@3.2.1", "tool-cli"]),
        ("/usr/bin/bunx", ["pkg@1.2.3-beta.1"]),
        ("uvx", ["duckduckgo-mcp-server==0.7.0"]),
        ("uvx", ["--from", "tool==1.0.0", "tool-cmd"]),
        ("uvx", ["pkg@1.0.0", "--with", "dep==2.0.0"]),
        ("pipx", ["run", "pkg==1.0.0"]),
        ("uv", ["tool", "run", "pkg==1.0.0"]),
        ("docker", ["run", "-i", "ghcr.io/x/y@sha256:" + "a" * 64]),
        ("node", ["./server.js"]),
        ("python", ["-m", "server"]),
    ],
)
def test_pinned(command: str, args: list[str]) -> None:
    assert floating_reference({"command": command, "args": args}) is None


@pytest.mark.parametrize(
    ("command", "args", "reason"),
    [
        ("npx", ["-y", "@upstash/context7-mcp"], "no version"),
        ("npx", ["pkg@latest"], "exact"),
        ("npx", ["pkg@^1.0.0"], "exact"),
        ("npx", [], "no version"),
        ("uvx", ["duckduckgo-mcp-server"], "no version"),
        ("uvx", ["pkg>=1.0"], "no version"),
        ("uvx", ["pkg==1.0.0", "--with", "dep"], "no version"),
        ("pipx", ["run", "pkg"], "no version"),
        ("docker", ["run", "-i", "ghcr.io/x/y:latest"], "digest"),
    ],
)
def test_floating(command: str, args: list[str], reason: str) -> None:
    problem = floating_reference({"command": command, "args": args})
    assert problem is not None
    assert reason in problem


def test_non_string_input_is_ignored() -> None:
    assert floating_reference({"command": 3}) is None
    assert floating_reference({"command": "npx", "args": [1]}) is None


@pytest.mark.parametrize(
    ("command", "args", "reason"),
    [
        ("npx", ["-y", "--registry=https://evil", "pkg@1.2.3"], "another registry"),
        ("npx", ["--registry", "https://evil", "pkg@1.2.3"], "another registry"),
        ("uvx", ["--index", "https://evil", "pkg==1.2.3"], "another index"),
        ("uvx", ["--default-index=https://evil", "pkg==1.2.3"], "another index"),
        (
            "docker",
            ["run", "-i", "evil/img:latest", f"acme/x@sha256:{'a' * 64}"],
            "digest",
        ),
    ],
)
def test_overrides_before_the_pinned_reference(
    command: str, args: list[str], reason: str
) -> None:
    problem = floating_reference({"command": command, "args": args})
    assert problem is not None
    assert reason in problem


def test_options_after_the_reference_are_the_servers() -> None:
    digest = "a" * 64
    pinned = [
        ("npx", ["-y", "pkg@1.2.3", "--registry", "x"]),
        ("uvx", ["pkg==1.2.3", "--index", "x"]),
        ("docker", ["run", "-i", "--rm", "-e", "K", f"acme/x@sha256:{digest}", "y"]),
    ]
    for command, args in pinned:
        assert floating_reference({"command": command, "args": args}) is None
