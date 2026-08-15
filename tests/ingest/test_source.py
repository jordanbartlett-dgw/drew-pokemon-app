from __future__ import annotations

from ingest.source import CSV_REPO, sparse_clone


def test_sparse_clone_issues_expected_git_commands(tmp_path, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("ingest.source.subprocess.run", fake_run)

    dest = tmp_path / "checkout"
    result = sparse_clone(CSV_REPO, ["data/v2/csv"], dest)

    assert result == dest
    assert calls[0][:3] == ["git", "clone", "--filter=blob:none"]
    assert "--sparse" in calls[0]
    assert CSV_REPO in calls[0]
    assert calls[1][:4] == ["git", "sparse-checkout", "set", "data/v2/csv"]


def test_sparse_clone_skips_when_already_present(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr("ingest.source.subprocess.run", lambda cmd, **kw: calls.append(cmd))

    dest = tmp_path / "checkout"
    (dest / ".git").mkdir(parents=True)

    assert sparse_clone(CSV_REPO, ["data/v2/csv"], dest) == dest
    assert calls == []
