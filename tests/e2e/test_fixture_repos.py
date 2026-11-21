from tests.support.fixture_repos import FixtureRepos, git


def test_fixture_repo_commit_reaches_the_bare_remote(
    fixture_repos: FixtureRepos,
) -> None:
    repo = fixture_repos.plain_git()
    first = repo.head
    second = repo.commit({"skills/review/SKILL.md": "changed\n"})
    assert first != second
    assert git(repo.bare, "rev-parse", "main") == second


def test_curated_clone_tracks_its_remote(fixture_repos: FixtureRepos) -> None:
    remote, clone = fixture_repos.curated()
    assert (clone / "README.md").is_file()
    assert git(clone, "rev-parse", "HEAD") == remote.head


def test_presets_build(fixture_repos: FixtureRepos) -> None:
    ap = fixture_repos.agent_plugins_marketplace()
    claude = fixture_repos.claude_marketplace()
    assert (ap.work / ".agents/plugins/marketplace.json").is_file()
    assert (claude.work / ".claude-plugin/marketplace.json").is_file()
