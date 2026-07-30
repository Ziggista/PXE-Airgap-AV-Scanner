from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_REPO_URL = "https://github.com/Ziggista/PXE-Airgap-AV-Scanner.git"
DEFAULT_BRANCH = "main"
LOCAL_DEPENDENCIES = ["paramiko", "pycdlib"]


def run_command(command: list[str], cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def require_command(command_name: str) -> str:
    resolved = shutil.which(command_name)
    if not resolved:
        raise FileNotFoundError(f"Required command not found on PATH: {command_name}")
    return resolved


def ensure_repo_checkout(destination: Path, repo_url: str, branch: str) -> Path:
    if (destination / ".git").exists():
        run_command(["git", "fetch", "origin", branch], cwd=destination)
        run_command(["git", "checkout", branch], cwd=destination)
        run_command(["git", "pull", "--ff-only", "origin", branch], cwd=destination)
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    run_command(["git", "clone", "--branch", branch, repo_url, str(destination)])
    return destination


def ensure_local_directories(repo_root: Path) -> tuple[Path, Path, Path]:
    local_root = repo_root / ".local"
    ssh_root = local_root / "ssh"
    ansible_root = local_root / "ansible"
    ssh_root.mkdir(parents=True, exist_ok=True)
    ansible_root.mkdir(parents=True, exist_ok=True)
    return local_root, ssh_root, ansible_root


def ensure_ssh_keypair(key_path: Path, comment: str) -> Path:
    if key_path.exists() and key_path.with_suffix(".pub").exists():
        return key_path.with_suffix(".pub")

    ssh_keygen = require_command("ssh-keygen")
    run_command([ssh_keygen, "-t", "ed25519", "-C", comment, "-f", str(key_path), "-N", ""])
    return key_path.with_suffix(".pub")


def create_or_update_virtualenv(repo_root: Path, python_executable: str, venv_path: Path | None = None) -> Path:
    target_venv = venv_path or (repo_root / ".local" / "venv")
    if not target_venv.exists():
        run_command([python_executable, "-m", "venv", str(target_venv)])

    venv_python = target_venv / ("Scripts" if os.name == "nt" else "bin") / "python.exe"
    if not venv_python.exists():
        venv_python = target_venv / ("Scripts" if os.name == "nt" else "bin") / "python"

    run_command([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])
    run_command([str(venv_python), "-m", "pip", "install", "-e", str(repo_root), *LOCAL_DEPENDENCIES])
    return target_venv


def default_destination() -> Path:
    if (Path.cwd() / ".git").exists():
        return Path.cwd()
    return Path.home() / "PXE-Airgap-AV-Scanner"


def write_local_summary(repo_root: Path, key_path: Path, public_key_path: Path, venv_path: Path) -> Path:
    summary_path = repo_root / ".local" / "ansible" / "bootstrap-summary.txt"
    public_key = public_key_path.read_text(encoding="utf-8").strip()
    summary = "\n".join(
        [
            f"repo_root={repo_root}",
            f"venv_path={venv_path}",
            f"private_key={key_path}",
            f"public_key={public_key_path}",
            f"public_key_value={public_key}",
        ]
    )
    summary_path.write_text(summary + "\n", encoding="utf-8")
    return summary_path


def print_bootstrap_summary(repo_root: Path, venv_path: Path, private_key: Path, summary_path: Path) -> None:
    print(f"Repository ready at: {repo_root}")
    print(f"Virtual environment: {venv_path}")
    print(f"SSH private key: {private_key}")
    print(f"Bootstrap summary: {summary_path}")
    print(f"Activate tooling with: {venv_path}\\Scripts\\activate")


def repo_python() -> str:
    return sys.executable
