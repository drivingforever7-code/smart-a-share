from __future__ import annotations

import asyncio

from app.main import health


def test_health_exposes_deployed_git_identity(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    monkeypatch.setenv("RENDER_GIT_BRANCH", "main")
    monkeypatch.setenv("RENDER_GIT_REPO_SLUG", "owner/repo")

    result = asyncio.run(health())

    assert result["status"] == "ok"
    assert result["git_commit"] == "abc123"
    assert result["git_branch"] == "main"
    assert result["git_repo"] == "owner/repo"
