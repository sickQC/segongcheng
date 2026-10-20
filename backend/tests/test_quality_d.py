"""Quality gates fail closed and never copy or report local secrets."""

import hashlib
import io
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest
from scripts import check_secrets, install_quality_tools


def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
    (root / ".gitignore").write_text(".env\n.local/\n", encoding="utf-8")
    (root / ".gitleaks.toml").write_text("[extend]\nuseDefault = true\n", encoding="utf-8")
    return root


def test_git_visible_snapshot_excludes_local_config_and_includes_new_sources(tmp_path):
    root = repo(tmp_path)
    (root / ".env").write_text("private sentinel", encoding="utf-8")
    (root / "new.py").write_text("x = 1\n", encoding="utf-8")
    destination = tmp_path / "snapshot"
    destination.mkdir()
    blocked, count = check_secrets.stage(root, destination)
    assert not blocked and count == 3
    assert (destination / "new.py").is_file() and not (destination / ".env").exists()


def test_tracked_sensitive_file_is_blocked_before_any_copy(tmp_path, monkeypatch):
    root = repo(tmp_path)
    (root / ".env").write_text("private sentinel", encoding="utf-8")
    subprocess.run(["git", "add", "-f", ".env"], cwd=root, check=True, capture_output=True)

    def forbidden_copy(*args):
        raise AssertionError("No content should be copied")

    monkeypatch.setattr(check_secrets.shutil, "copyfile", forbidden_copy)
    blocked, count = check_secrets.stage(root, tmp_path / "unused")
    assert blocked == [".env"] and count == 0


@pytest.mark.parametrize("name", ["deploy/.env.deploy", "backup.db", "tls/private.key", ".local/result.json"])
def test_sensitive_deliverables_are_blocked(name):
    assert check_secrets.forbidden(Path(name))
    assert not check_secrets.forbidden(Path("deploy/.env.example"))


def test_sanitization_never_exports_match_or_secret(tmp_path):
    rows = [{"File": str(tmp_path / "a.py"), "StartLine": 7, "RuleID": "test",
             "Secret": "sensitive sentinel", "Match": "private content", "Author": "private author"}]
    result = check_secrets.sanitized(rows, tmp_path)
    assert result == [{"file": "a.py", "line": 7, "rule": "test"}]
    assert "sentinel" not in json.dumps(result) and "private" not in json.dumps(result)


@pytest.mark.parametrize("exit_code,write_report", [(2, False), (1, False), (1, True)])
def test_detector_failure_is_never_a_pass(tmp_path, monkeypatch, exit_code, write_report):
    root = repo(tmp_path)

    def run(command, **kwargs):
        if command[1] == "version":
            return subprocess.CompletedProcess(command, 0, stdout=check_secrets.VERSION)
        if command[0] == "git":
            return subprocess.CompletedProcess(command, 0, stdout=b".gitleaks.toml\0")
        report = Path(command[command.index("--report-path") + 1])
        if write_report:
            report.write_text("[]", encoding="utf-8")
        return subprocess.CompletedProcess(command, exit_code, stdout=b"sensitive sentinel")

    monkeypatch.setattr(check_secrets.subprocess, "run", run)
    with pytest.raises(ValueError, match="detector") as error:
        check_secrets.scan(root, Path("fake-scanner"))
    assert "sentinel" not in str(error.value)


def test_binary_checksum_rejected_before_archive_read():
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        install_quality_tools.verified_binary(b"tampered", "0" * 64, "Windows")


def test_installer_reads_only_expected_archive_member():
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr("gitleaks.exe", b"verified test binary")
        archive.writestr("../../escape.txt", b"not extracted")
    value = raw.getvalue()
    result = install_quality_tools.verified_binary(value, hashlib.sha256(value).hexdigest(), "Windows")
    assert result == b"verified test binary"
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as archive:
        member = tarfile.TarInfo("gitleaks")
        member.size = 4
        archive.addfile(member, io.BytesIO(b"tool"))
        link = tarfile.TarInfo("../../escape")
        link.type = tarfile.SYMTYPE
        link.linkname = "/outside"
        archive.addfile(link)
    value = raw.getvalue()
    assert install_quality_tools.verified_binary(value, hashlib.sha256(value).hexdigest(), "Linux") == b"tool"
