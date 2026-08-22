"""Build-metadata resolution: baked env first, git fallback, neutral default."""

import subprocess

from schematalog.app import __version__
from schematalog.app.presentation.helpers import buildinfo


def test_commit_prefers_baked_env(monkeypatch):
    monkeypatch.setenv("GIT_COMMIT", "deadbee")
    assert buildinfo.commit() == "deadbee"


def test_commit_falls_back_to_git_head(monkeypatch):
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.setattr(buildinfo.shutil, "which", lambda _: "/usr/bin/git")
    monkeypatch.setattr(
        buildinfo.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="abc1234\n", stderr=""),
    )
    assert buildinfo.commit() == "abc1234"


def test_commit_unknown_when_git_absent(monkeypatch):
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.setattr(buildinfo.shutil, "which", lambda _: None)
    assert buildinfo.commit() == "unknown"


def test_commit_unknown_on_git_failure(monkeypatch):
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.setattr(buildinfo.shutil, "which", lambda _: "/usr/bin/git")

    def _boom(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr(buildinfo.subprocess, "run", _boom)
    assert buildinfo.commit() == "unknown"


def test_commit_date_prefers_baked_env(monkeypatch):
    monkeypatch.setenv("GIT_COMMIT_DATE", "2026-06-07")
    assert buildinfo.commit_date() == "2026-06-07"


def test_commit_date_empty_when_git_absent(monkeypatch):
    monkeypatch.delenv("GIT_COMMIT_DATE", raising=False)
    monkeypatch.setattr(buildinfo.shutil, "which", lambda _: None)
    assert buildinfo.commit_date() == ""


def test_app_version_matches_code_constant():
    assert buildinfo.app_version() == __version__
