"""Scan a Git-visible file snapshot; never print detector output or secret material."""

import argparse
import json
import os
import random
import shutil
import string
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "8.30.1"


def forbidden(path):
    parts = path.parts
    name = path.name.lower()
    return (name.startswith(".env") and name != ".env.example") or (
        bool({".git", ".local", ".venv", "node_modules", "__pycache__"} & set(parts))
        or name.endswith((".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3", ".p12", ".pfx", ".key"))
        or name in {"id_rsa", "id_ed25519"}
    )


def visible_files(root):
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                            cwd=root, capture_output=True, check=True)
    return sorted({Path(p.decode("utf-8")) for p in result.stdout.split(b"\0") if p})


def stage(root, destination):
    paths = visible_files(root)
    blocked = [p.as_posix() for p in paths if forbidden(p)]
    if blocked:
        return blocked, 0
    count = 0
    for relative in paths:
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Git-visible path must be a relative file inside the workspace")
        source = root / relative
        if source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError("Git-visible symlinks or paths outside the workspace are not scanned")
        if not source.is_file():
            continue  # A tracked file deleted in the current worktree is absent from this snapshot.
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        count += 1
    return [], count


def sanitized(rows, snapshot):
    findings = []
    for row in rows:
        path = Path(row.get("File", ""))
        if path.is_absolute():
            try:
                path = path.relative_to(snapshot)
            except ValueError:
                path = Path("unresolved-file")
        findings.append({"file": path.as_posix(), "line": row.get("StartLine"), "rule": row.get("RuleID")})
    return findings


def scan(root, executable, history=False):
    root = Path(root).resolve()
    version = subprocess.run([str(executable), "version"], capture_output=True, text=True, check=True)
    if version.stdout.strip() != VERSION:
        raise ValueError("Unexpected Gitleaks version; install the pinned project tool")
    local = root / ".local"
    local.mkdir(exist_ok=True)
    if not local.resolve().is_relative_to(root):
        raise ValueError("Project temporary directory must stay inside the workspace")
    with tempfile.TemporaryDirectory(prefix="secret-scan-", dir=local) as temporary:
        work = Path(temporary)
        snapshot = work / "snapshot"
        snapshot.mkdir()
        blocked, count = stage(root, snapshot)
        report = {"version": VERSION, "scope": "Git-visible current worktree", "files": count,
                  "blocked_files": blocked, "findings": [], "history_scanned": history,
                  "secret_values_in_report": False}
        if blocked:
            report["status"] = "blocked-sensitive-files"
            return report
        modes = [("dir", snapshot)] + ([("git", root)] if history else [])
        for index, (mode, target) in enumerate(modes):
            raw_report = work / f"detector-{index}.json"
            command = [str(executable), mode, str(target), "--config", str(root / ".gitleaks.toml"),
                       "--no-banner", "--no-color", "--redact=100", "--log-level=error",
                       "--ignore-gitleaks-allow", "--gitleaks-ignore-path", str(work / "no-ignore-file"),
                       "--max-archive-depth=0", "--report-format=json", "--report-path", str(raw_report)]
            if mode == "git":
                command += ["--log-opts=--all"]
            # Do not echo stdout/stderr even if the external tool fails.
            result = subprocess.run(command, cwd=root, capture_output=True, timeout=240)
            if result.returncode not in (0, 1) or not raw_report.is_file():
                raise ValueError("Secret detector failed; raw output suppressed")
            rows = json.loads(raw_report.read_text(encoding="utf-8")) or []
            if result.returncode == 1 and not rows:
                raise ValueError("Secret detector returned failure without findings")
            report["findings"].extend({**r, "scope": mode} for r in sanitized(rows, snapshot))
        report["status"] = "findings" if report["findings"] else "passed"
        return report


def self_test(executable):
    local = ROOT / ".local"
    local.mkdir(exist_ok=True)
    if not local.resolve().is_relative_to(ROOT):
        raise ValueError("Self-test directory must remain inside the workspace")
    with tempfile.TemporaryDirectory(prefix="secret-canary-", dir=local) as directory:
        root = Path(directory).resolve()
        subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True, check=True)
        (root / ".gitignore").write_text(".local/\n.env\n", encoding="utf-8")
        (root / ".gitleaks.toml").write_text("[extend]\nuseDefault = true\n", encoding="utf-8")
        (root / "probe.py").write_text("x = 1\n", encoding="utf-8")
        if scan(root, executable)["status"] != "passed":
            raise ValueError("Clean self-test failed")
        # Invalid, generated canary; no real credential is used or printed.
        canary = "ghp_" + "".join(random.Random(731).choices(string.ascii_letters + string.digits, k=36))
        (root / "probe.py").write_text(f'API_TOKEN = "{canary}"\n', encoding="utf-8")
        result = scan(root, executable)
        if result["status"] != "findings" or canary in json.dumps(result):
            raise ValueError("Canary detection or report redaction failed")
        (root / ".env").write_text("local-only-sentinel", encoding="utf-8")
        subprocess.run(["git", "add", "-f", ".env"], cwd=root, capture_output=True, check=True)
        if scan(root, executable)["status"] != "blocked-sensitive-files":
            raise ValueError("Sensitive-file self-test failed")


def main():
    parser = argparse.ArgumentParser()
    default = ROOT / ".local/tools/gitleaks-8.30.1/gitleaks"
    parser.add_argument("--gitleaks", type=Path, default=default.with_suffix(".exe") if os.name == "nt" else default)
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--report", type=Path, default=ROOT / ".local/ci/secret-scan-summary.json")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test(args.gitleaks.resolve())
            print("Scanner self-test passed: clean input, invalid canary, redacted summary and sensitive-file block.")
            return
        report = scan(ROOT, args.gitleaks.resolve(), args.history)
    except (OSError, ValueError, subprocess.SubprocessError):
        print("Secret scanning could not complete. Check tool installation and Git configuration; raw output suppressed.")
        raise SystemExit(2) from None
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Secret scan: {report['status']}; files={report['files']}; findings={len(report['findings'])}; blocked={len(report['blocked_files'])}. Values are never displayed.")
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
