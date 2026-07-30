from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from avtooling.local_repo import (
    DEFAULT_BRANCH,
    DEFAULT_REPO_URL,
    create_or_update_virtualenv,
    default_destination,
    ensure_local_directories,
    ensure_repo_checkout,
    ensure_ssh_keypair,
    print_bootstrap_summary,
    repo_python,
    require_command,
    write_local_summary,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clone or refresh the PXE Airgap AV Scanner repo on Windows and install local helper tooling."
    )
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--destination", default=str(default_destination()))
    parser.add_argument("--python", default=repo_python())
    args = parser.parse_args()

    require_command("git")
    require_command("ssh-keygen")

    repo_root = ensure_repo_checkout(Path(args.destination).resolve(), args.repo_url, args.branch)
    _, ssh_root, _ = ensure_local_directories(repo_root)
    key_path = ssh_root / "ziggi-py-host-ed25519"
    public_key_path = ensure_ssh_keypair(key_path, "ziggi-py-control-host")
    venv_path = create_or_update_virtualenv(repo_root, args.python)
    summary_path = write_local_summary(repo_root, key_path, public_key_path, venv_path)
    print_bootstrap_summary(repo_root, venv_path, key_path, summary_path)


if __name__ == "__main__":
    main()
