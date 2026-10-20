"""Install a pinned, SHA256-verified scanner inside the project; no system changes."""

import hashlib
import io
import platform
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "8.30.1"
ASSETS = {
    "Windows": ("windows_x64.zip", "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e"),
    "Linux": ("linux_x64.tar.gz", "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"),
}


def verified_binary(raw, checksum, system):
    if hashlib.sha256(raw).hexdigest() != checksum:
        raise ValueError("Scanner archive SHA256 mismatch; nothing installed")
    # Read only the single expected member, never extract archive paths onto disk.
    if system == "Windows":
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            return archive.read("gitleaks.exe")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        member = archive.getmember("gitleaks")
        if not member.isfile():
            raise ValueError("Scanner archive member must be a regular file")
        return archive.extractfile(member).read()


def main():
    system = platform.system()
    if system not in ASSETS or platform.machine().lower() not in ("amd64", "x86_64"):
        raise SystemExit("Project scanner installer supports Windows/Linux x64 only")
    suffix, checksum = ASSETS[system]
    url = f"https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/gitleaks_{VERSION}_{suffix}"
    with urllib.request.urlopen(url, timeout=60) as response:
        raw = response.read()
    binary = verified_binary(raw, checksum, system)
    directory = ROOT / f".local/tools/gitleaks-{VERSION}"
    if not directory.resolve().is_relative_to(ROOT):
        raise SystemExit("Tool directory must remain inside the workspace")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / ("gitleaks.exe" if system == "Windows" else "gitleaks")
    if target.exists():
        if target.is_symlink() or target.read_bytes() != binary:
            raise SystemExit("Existing scanner differs from verified release; it was not overwritten")
    else:
        with target.open("xb") as output:
            output.write(binary)
    if system == "Linux":
        target.chmod(0o755)
    print(f"Gitleaks {VERSION} verified and available in the project's .local/tools directory.")


if __name__ == "__main__":
    main()
