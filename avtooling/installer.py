from __future__ import annotations

import argparse
import subprocess
import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from avtooling.hyperv_lab import (
    DEFAULT_BRANCH as DEFAULT_DEPLOY_BRANCH,
    DEFAULT_CLOUDINIT_OUTPUT,
    DEFAULT_HYPERV_ROOT,
    DEFAULT_OLD_ROOT,
    DEFAULT_REMOTE_REPO_ROOT,
    DEFAULT_REPO_URL as DEFAULT_DEPLOY_REPO_URL,
    PXE_TEST_SPEC,
    SERVER_SPECS,
    build_seed_isos,
    create_fresh_vms,
    deploy_from_control_node,
    ensure_switch,
    rotate_existing_vms,
    start_vms,
    validate_prerequisites,
    verify_pxe_reservation,
    wait_for_tcp,
    write_summary,
)
from avtooling.local_repo import (
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


DEFAULT_STATE_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PXE-Airgap-AV-Scanner"
DEFAULT_SETTINGS_PATH = DEFAULT_STATE_ROOT / "installer-settings.json"


@dataclass
class InstallerSettings:
    repo_url: str = DEFAULT_DEPLOY_REPO_URL
    branch: str = DEFAULT_DEPLOY_BRANCH
    repo_destination: str = str(default_destination())
    python_executable: str = repo_python()
    state_root: str = str(DEFAULT_STATE_ROOT)
    private_key_path: str = str(DEFAULT_STATE_ROOT / "ssh" / "ziggi-py-host-ed25519")
    hyperv_active_root: str = str(DEFAULT_HYPERV_ROOT)
    hyperv_old_root: str = str(DEFAULT_OLD_ROOT)
    cloudinit_output_root: str = str(DEFAULT_CLOUDINIT_OUTPUT)
    hyperv_switch_name: str = "AV-PXE-Lab"
    remote_repo_root: str = DEFAULT_REMOTE_REPO_ROOT
    deploy_after_bootstrap: bool = False
    rotate_existing_vms: bool = True


@dataclass(frozen=True)
class DependencyCheck:
    command: str
    winget_id: str | None
    description: str


DEPENDENCY_CHECKS = (
    DependencyCheck("git", "Git.Git", "Git CLI"),
    DependencyCheck("ssh-keygen", None, "OpenSSH client tooling"),
    DependencyCheck("powershell", None, "Windows PowerShell"),
)


def _state_root_from_settings(settings: InstallerSettings) -> Path:
    return Path(settings.state_root).resolve()


def _settings_path(state_root: Path) -> Path:
    return state_root / "installer-settings.json"


def _installer_summary_path(state_root: Path) -> Path:
    return state_root / "installer-summary.txt"


def load_settings(path: Path) -> InstallerSettings:
    if not path.exists():
        return InstallerSettings()
    data = json.loads(path.read_text(encoding="utf-8"))
    return InstallerSettings(**data)


def save_settings(settings: InstallerSettings, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), indent=2) + "\n", encoding="utf-8")


def prompt_text(label: str, current: str) -> str:
    value = input(f"{label} [{current}]: ").strip()
    return value or current


def prompt_bool(label: str, current: bool) -> bool:
    default = "Y/n" if current else "y/N"
    value = input(f"{label} [{default}]: ").strip().lower()
    if not value:
        return current
    return value in {"y", "yes", "true", "1"}


def seed_settings_interactive(existing: InstallerSettings) -> InstallerSettings:
    print("Seeding installer settings. Press Enter to keep each default.")
    settings = InstallerSettings(
        repo_url=prompt_text("Repository URL", existing.repo_url),
        branch=prompt_text("Repository branch", existing.branch),
        repo_destination=prompt_text("Local repository destination", existing.repo_destination),
        python_executable=prompt_text("Python executable", existing.python_executable),
        state_root=prompt_text("State root outside the repository", existing.state_root),
        private_key_path=prompt_text("SSH private key path", existing.private_key_path),
        hyperv_active_root=prompt_text("Hyper-V active VM root", existing.hyperv_active_root),
        hyperv_old_root=prompt_text("Hyper-V rotated VM root", existing.hyperv_old_root),
        cloudinit_output_root=prompt_text("Cloud-init ISO output root", existing.cloudinit_output_root),
        hyperv_switch_name=prompt_text("PXE Hyper-V switch name", existing.hyperv_switch_name),
        remote_repo_root=prompt_text("Remote control-node repo path", existing.remote_repo_root),
        deploy_after_bootstrap=prompt_bool("Run full Hyper-V deploy after bootstrap", existing.deploy_after_bootstrap),
        rotate_existing_vms=prompt_bool("Rotate any existing lab VMs during deploy", existing.rotate_existing_vms),
    )
    return settings


def ensure_state_directories(state_root: Path, private_key_path: Path) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    private_key_path.parent.mkdir(parents=True, exist_ok=True)


def ensure_dependency(dep: DependencyCheck, *, non_interactive: bool) -> None:
    if shutil.which(dep.command):
        return

    print(f"Missing dependency: {dep.description} ({dep.command})")
    if dep.winget_id and shutil.which("winget"):
        should_install = non_interactive or prompt_bool(f"Install {dep.description} with winget now", True)
        if should_install:
            subprocess.run(
                [
                    "winget",
                    "install",
                    "--id",
                    dep.winget_id,
                    "--exact",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ],
                check=True,
            )
    require_command(dep.command)


def ensure_dependencies(*, non_interactive: bool) -> None:
    for dep in DEPENDENCY_CHECKS:
        ensure_dependency(dep, non_interactive=non_interactive)


def write_installer_summary(
    state_root: Path,
    settings_path: Path,
    repo_root: Path,
    private_key_path: Path,
    venv_path: Path,
    deploy_summary_path: Path | None,
) -> Path:
    lines = [
        f"repo_root={repo_root}",
        f"venv_path={venv_path}",
        f"private_key={private_key_path}",
        f"settings_file={settings_path}",
    ]
    if deploy_summary_path:
        lines.append(f"deploy_summary={deploy_summary_path}")
    summary_path = _installer_summary_path(state_root)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary_path


def run_bootstrap(settings: InstallerSettings) -> tuple[Path, Path, Path]:
    repo_root = ensure_repo_checkout(
        Path(settings.repo_destination).resolve(),
        settings.repo_url,
        settings.branch,
    )
    _, _, _ = ensure_local_directories(repo_root)
    private_key_path = Path(settings.private_key_path).resolve()
    public_key_path = ensure_ssh_keypair(private_key_path, "ziggi-py-control-host")
    venv_path = create_or_update_virtualenv(repo_root, settings.python_executable)
    summary_path = write_local_summary(repo_root, private_key_path, public_key_path, venv_path)
    print_bootstrap_summary(repo_root, venv_path, private_key_path, summary_path)
    return repo_root, private_key_path, venv_path


def run_deploy(settings: InstallerSettings, repo_root: Path, private_key_path: Path) -> Path:
    validate_prerequisites(repo_root, private_key_path)
    ensure_switch(settings.hyperv_switch_name)
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    seeds = build_seed_isos(repo_root, run_id, Path(settings.cloudinit_output_root).resolve())
    all_vm_names = [spec.name for spec in SERVER_SPECS] + [PXE_TEST_SPEC.name]
    rotated = {} if not settings.rotate_existing_vms else rotate_existing_vms(
        all_vm_names,
        Path(settings.hyperv_old_root).resolve(),
    )
    create_fresh_vms(Path(settings.hyperv_active_root).resolve(), seeds)
    start_vms([spec.name for spec in SERVER_SPECS])
    for spec in SERVER_SPECS:
        if spec.management_ip:
            wait_for_tcp(spec.management_ip, 22, timeout_seconds=900)
    deploy_from_control_node(
        repo_root,
        private_key_path,
        repo_url=settings.repo_url,
        branch=settings.branch,
        remote_repo_root=settings.remote_repo_root,
    )
    start_vms([PXE_TEST_SPEC.name])
    lease_snapshot = verify_pxe_reservation(private_key_path)
    return write_summary(repo_root, rotated, seeds, lease_snapshot)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Windows-first installer and deploy wrapper for the PXE Airgap AV Scanner lab."
    )
    parser.add_argument("--settings-file", default=str(DEFAULT_SETTINGS_PATH))
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--deploy", action="store_true")
    parser.add_argument("--skip-deploy", action="store_true")
    parser.add_argument("--reset-settings", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings_path = Path(args.settings_file).resolve()
    existing = InstallerSettings() if args.reset_settings else load_settings(settings_path)
    settings = existing if args.non_interactive else seed_settings_interactive(existing)
    if args.deploy:
        settings.deploy_after_bootstrap = True
    if args.skip_deploy:
        settings.deploy_after_bootstrap = False

    state_root = _state_root_from_settings(settings)
    private_key_path = Path(settings.private_key_path).resolve()
    ensure_state_directories(state_root, private_key_path)
    save_settings(settings, settings_path)
    ensure_dependencies(non_interactive=args.non_interactive)
    repo_root, private_key_path, venv_path = run_bootstrap(settings)
    deploy_summary_path = run_deploy(settings, repo_root, private_key_path) if settings.deploy_after_bootstrap else None
    installer_summary_path = write_installer_summary(
        state_root,
        settings_path,
        repo_root,
        private_key_path,
        venv_path,
        deploy_summary_path,
    )
    print(f"Installer settings: {settings_path}")
    print(f"Installer summary: {installer_summary_path}")
    if deploy_summary_path:
        print(f"Deploy summary: {deploy_summary_path}")


if __name__ == "__main__":
    main()
