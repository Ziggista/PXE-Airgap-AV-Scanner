from __future__ import annotations

import argparse
import shlex
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from avtooling.cloudinit_iso import build_cloudinit_iso
from avtooling.hyperv_inventory import HyperVInventoryError, discover_vm_addresses, update_inventory_hosts_file
from avtooling.local_repo import require_command


DEFAULT_SWITCH_NAME = "AV-PXE-Lab"
DEFAULT_DEFAULT_SWITCH = "Default Switch"
DEFAULT_HYPERV_ROOT = Path(r"D:\AV\hyperv\active")
DEFAULT_OLD_ROOT = Path(r"D:\AV\hyperv\old")
DEFAULT_CLOUDINIT_OUTPUT = Path(r"D:\AV\cloudinit")
DEFAULT_BASE_VHDX = Path(r"D:\AV\cloud-images\ubuntu-26.04-server-cloudimg-amd64.vhdx")
DEFAULT_REPO_URL = "https://github.com/Ziggista/PXE-Airgap-AV-Scanner.git"
DEFAULT_BRANCH = "main"
DEFAULT_REMOTE_REPO_ROOT = "/opt/av-pxe-tooling"


@dataclass(frozen=True)
class VmSpec:
    name: str
    hostname: str
    management_ip: str | None
    default_switch_mac: str | None
    startup_memory_bytes: int
    dynamic_memory: bool
    minimum_memory_bytes: int
    maximum_memory_bytes: int
    processors: int
    generation: int = 2
    secure_boot: bool = True
    secure_boot_template: str = "MicrosoftUEFICertificateAuthority"
    create_disk: bool = True
    disk_size_bytes: int = 32 * 1024**3
    seed_name: str | None = None
    extra_adapters: tuple[tuple[str, str, str], ...] = ()
    first_boot_network: bool = False


SERVER_SPECS = (
    VmSpec(
        name="av-control-node-26",
        hostname="av-control-node",
        management_ip="172.23.23.27",
        default_switch_mac="00:15:5d:01:1c:08",
        startup_memory_bytes=4 * 1024**3,
        dynamic_memory=True,
        minimum_memory_bytes=2 * 1024**3,
        maximum_memory_bytes=8 * 1024**3,
        processors=2,
        disk_size_bytes=32 * 1024**3,
        seed_name="control-node",
    ),
    VmSpec(
        name="av-repo-vm",
        hostname="av-repo-vm",
        management_ip="172.23.27.229",
        default_switch_mac="00:15:5d:01:1c:09",
        startup_memory_bytes=4 * 1024**3,
        dynamic_memory=True,
        minimum_memory_bytes=2 * 1024**3,
        maximum_memory_bytes=8 * 1024**3,
        processors=2,
        disk_size_bytes=48 * 1024**3,
        seed_name="repo-vm",
    ),
    VmSpec(
        name="av-build-vm",
        hostname="av-build-vm",
        management_ip="172.23.30.254",
        default_switch_mac="00:15:5d:01:1c:0a",
        startup_memory_bytes=8 * 1024**3,
        dynamic_memory=False,
        minimum_memory_bytes=2 * 1024**3,
        maximum_memory_bytes=8 * 1024**3,
        processors=4,
        disk_size_bytes=64 * 1024**3,
        seed_name="build-vm",
        extra_adapters=(("PXE Lab", DEFAULT_SWITCH_NAME, "00:15:5d:01:1c:0c"),),
    ),
)

PXE_TEST_SPEC = VmSpec(
    name="av-pxe-uefi-test-vm",
    hostname="av-pxe-client",
    management_ip=None,
    default_switch_mac="00:15:5d:01:1c:0e",
    startup_memory_bytes=12 * 1024**3,
    dynamic_memory=False,
    minimum_memory_bytes=512 * 1024**2,
    maximum_memory_bytes=1024 * 1024**4,
    processors=4,
    secure_boot=False,
    secure_boot_template="MicrosoftWindows",
    create_disk=False,
    first_boot_network=True,
)


class HyperVLabError(RuntimeError):
    pass


def _run(args: list[str], *, cwd: Path | None = None, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def _run_powershell(script: str, *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    args = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]
    return _run(args, capture_output=capture_output)


def _ssh_base(private_key: Path) -> list[str]:
    return [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-i",
        str(private_key),
    ]


def _scp_base(private_key: Path) -> list[str]:
    return [
        "scp",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-i",
        str(private_key),
    ]


def _remote_shell_quote(value: str) -> str:
    return shlex.quote(value)


def validate_prerequisites(repo_root: Path, private_key: Path) -> None:
    require_command("git")
    require_command("ssh")
    require_command("scp")
    if not private_key.exists():
        raise HyperVLabError(f"SSH private key not found: {private_key}")
    if not DEFAULT_BASE_VHDX.exists():
        raise HyperVLabError(f"Base Hyper-V cloud image not found: {DEFAULT_BASE_VHDX}")
    if not (repo_root / "inventories" / "lab" / "group_vars" / "all" / "license_acceptance.yml").exists():
        raise HyperVLabError(
            "Local operator-managed inventories/lab/group_vars/all/license_acceptance.yml is required."
        )
    if not (repo_root / "runtime" / "downloads" / "ubuntu-26.04-desktop-amd64.iso").exists():
        raise HyperVLabError(
            "Local upstream desktop ISO is required at runtime/downloads/ubuntu-26.04-desktop-amd64.iso."
        )


def build_seed_isos(
    repo_root: Path,
    run_id: str,
    output_root: Path = DEFAULT_CLOUDINIT_OUTPUT,
) -> dict[str, Path]:
    seeds: dict[str, Path] = {}
    for seed_name in ("control-node", "repo-vm", "build-vm"):
        source_dir = repo_root / "cloudinit" / seed_name
        if not source_dir.exists():
            raise HyperVLabError(f"Missing cloud-init seed directory: {source_dir}")
        output_iso = output_root / f"{seed_name}-seed-{run_id}.iso"
        build_cloudinit_iso(source_dir, output_iso)
        seeds[seed_name] = output_iso
    return seeds


def ensure_switch(switch_name: str = DEFAULT_SWITCH_NAME) -> None:
    script = rf"""
$ErrorActionPreference = 'Stop'
if (-not (Get-VMSwitch -Name '{switch_name}' -ErrorAction SilentlyContinue)) {{
  New-VMSwitch -Name '{switch_name}' -SwitchType Internal | Out-Null
}}
"""
    _run_powershell(script)


def rotate_existing_vms(
    vm_names: list[str],
    old_root: Path = DEFAULT_OLD_ROOT,
    active_root: Path = DEFAULT_HYPERV_ROOT,
) -> dict[str, str]:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    renamed: dict[str, str] = {}
    old_root.mkdir(parents=True, exist_ok=True)
    for vm_name in vm_names:
        old_name = f"{vm_name}.old.{timestamp}"
        source_root = active_root / vm_name
        archive_root = old_root / old_name
        script = rf"""
$ErrorActionPreference = 'Stop'
$sourceRoot = '{source_root}'
$archiveRoot = '{archive_root}'
$vm = Get-VM -Name '{vm_name}' -ErrorAction SilentlyContinue
if (-not $vm) {{
  $vm = Get-VM | Where-Object {{
    $_.Path -like "$sourceRoot*" -or
    $_.ConfigurationLocation -like "$sourceRoot*" -or
    $_.SnapshotFileLocation -like "$sourceRoot*" -or
    $_.SmartPagingFilePath -like "$sourceRoot*"
  }} | Select-Object -First 1
}}
if ($vm) {{
  Stop-VM -VM $vm -TurnOff -Force -ErrorAction SilentlyContinue | Out-Null
  if ($vm.Name -ne '{old_name}') {{
    Rename-VM -VM $vm -NewName '{old_name}'
    $vm = Get-VM -Name '{old_name}'
  }}
  Remove-VM -VM $vm -Force
}}
if (Test-Path -LiteralPath $sourceRoot) {{
  if (Test-Path -LiteralPath $archiveRoot) {{
    Remove-Item -LiteralPath $archiveRoot -Recurse -Force -ErrorAction Stop
  }}
  Move-Item -LiteralPath $sourceRoot -Destination $archiveRoot
}}
"""
        _run_powershell(script)
        renamed[vm_name] = old_name
    return renamed


def _create_server_vm(spec: VmSpec, seeds: dict[str, Path], active_root: Path) -> None:
    vm_root = active_root / spec.name
    config_root = vm_root / spec.name
    vhd_path = vm_root / f"{spec.name}.vhdx"
    seed_iso = seeds[spec.seed_name or ""]
    memory_command = (
        f"Set-VMMemory -VMName '{spec.name}' -DynamicMemoryEnabled $true "
        f"-MinimumBytes {spec.minimum_memory_bytes} -StartupBytes {spec.startup_memory_bytes} "
        f"-MaximumBytes {spec.maximum_memory_bytes}"
        if spec.dynamic_memory
        else f"Set-VMMemory -VMName '{spec.name}' -DynamicMemoryEnabled $false "
        f"-StartupBytes {spec.startup_memory_bytes}"
    )
    script = rf"""
$ErrorActionPreference = 'Stop'
$vmRoot = '{vm_root}'
$configRoot = '{config_root}'
$vhdPath = '{vhd_path}'
$baseVhdx = '{DEFAULT_BASE_VHDX}'
$seedIso = '{seed_iso}'

if (Get-VM -Name '{spec.name}' -ErrorAction SilentlyContinue) {{
  Stop-VM -Name '{spec.name}' -TurnOff -Force -ErrorAction SilentlyContinue | Out-Null
  Remove-VM -Name '{spec.name}' -Force
}}

if (Test-Path -LiteralPath $vmRoot) {{
  Remove-Item -LiteralPath $vmRoot -Recurse -Force
}}

New-Item -ItemType Directory -Path $vmRoot -Force | Out-Null
Copy-Item -LiteralPath $baseVhdx -Destination $vhdPath -Force
Resize-VHD -Path $vhdPath -SizeBytes {spec.disk_size_bytes}

New-VM -Name '{spec.name}' -Generation {spec.generation} -MemoryStartupBytes {spec.startup_memory_bytes} `
  -VHDPath $vhdPath -Path $configRoot -SwitchName '{DEFAULT_DEFAULT_SWITCH}' | Out-Null

Set-VMProcessor -VMName '{spec.name}' -Count {spec.processors}
{memory_command}
Set-VM -Name '{spec.name}' -AutomaticCheckpointsEnabled $false
Set-VMNetworkAdapter -VMName '{spec.name}' -StaticMacAddress '{spec.default_switch_mac.replace(':', '')}'
Set-VMFirmware -VMName '{spec.name}' -EnableSecureBoot {'On' if spec.secure_boot else 'Off'} `
  -SecureBootTemplate '{spec.secure_boot_template}'

Add-VMDvdDrive -VMName '{spec.name}' -Path $seedIso | Out-Null
$hdd = Get-VMHardDiskDrive -VMName '{spec.name}' | Select-Object -First 1
Set-VMFirmware -VMName '{spec.name}' -FirstBootDevice $hdd
"""
    _run_powershell(script)

    for adapter_name, switch_name, mac_address in spec.extra_adapters:
        adapter_script = rf"""
$ErrorActionPreference = 'Stop'
Add-VMNetworkAdapter -VMName '{spec.name}' -Name '{adapter_name}' -SwitchName '{switch_name}' | Out-Null
Set-VMNetworkAdapter -VMName '{spec.name}' -Name '{adapter_name}' -StaticMacAddress '{mac_address.replace(':', '')}'
"""
        _run_powershell(adapter_script)


def _create_pxe_test_vm(spec: VmSpec, active_root: Path) -> None:
    vm_root = active_root / spec.name
    config_root = vm_root / spec.name
    memory_command = (
        f"Set-VMMemory -VMName '{spec.name}' -DynamicMemoryEnabled $true "
        f"-MinimumBytes {spec.minimum_memory_bytes} -StartupBytes {spec.startup_memory_bytes} "
        f"-MaximumBytes {spec.maximum_memory_bytes}"
        if spec.dynamic_memory
        else f"Set-VMMemory -VMName '{spec.name}' -DynamicMemoryEnabled $false "
        f"-StartupBytes {spec.startup_memory_bytes}"
    )
    script = rf"""
$ErrorActionPreference = 'Stop'
$vmRoot = '{vm_root}'
$configRoot = '{config_root}'

if (Get-VM -Name '{spec.name}' -ErrorAction SilentlyContinue) {{
  Stop-VM -Name '{spec.name}' -TurnOff -Force -ErrorAction SilentlyContinue | Out-Null
  Remove-VM -Name '{spec.name}' -Force
}}

if (Test-Path -LiteralPath $vmRoot) {{
  Remove-Item -LiteralPath $vmRoot -Recurse -Force
}}

New-Item -ItemType Directory -Path $vmRoot -Force | Out-Null
New-VM -Name '{spec.name}' -Generation {spec.generation} -NoVHD -MemoryStartupBytes {spec.startup_memory_bytes} `
  -Path $configRoot -SwitchName '{DEFAULT_SWITCH_NAME}' | Out-Null

Set-VMProcessor -VMName '{spec.name}' -Count {spec.processors}
{memory_command}
Set-VM -Name '{spec.name}' -AutomaticCheckpointsEnabled $false
Set-VMNetworkAdapter -VMName '{spec.name}' -StaticMacAddress '{spec.default_switch_mac.replace(':', '')}'
Set-VMFirmware -VMName '{spec.name}' -EnableSecureBoot {'On' if spec.secure_boot else 'Off'} `
  -SecureBootTemplate '{spec.secure_boot_template}'
$nic = Get-VMNetworkAdapter -VMName '{spec.name}' | Select-Object -First 1
Set-VMFirmware -VMName '{spec.name}' -FirstBootDevice $nic
"""
    _run_powershell(script)


def create_fresh_vms(active_root: Path, seeds: dict[str, Path]) -> None:
    active_root.mkdir(parents=True, exist_ok=True)
    for spec in SERVER_SPECS:
        _create_server_vm(spec, seeds, active_root)
    _create_pxe_test_vm(PXE_TEST_SPEC, active_root)


def start_vms(vm_names: list[str]) -> None:
    joined = ",".join(f"'{name}'" for name in vm_names)
    script = rf"""
$ErrorActionPreference = 'Stop'
foreach ($vm in Get-VM -Name {joined}) {{
  Start-VM -VM $vm | Out-Null
}}
"""
    _run_powershell(script)


def wait_for_tcp(host: str, port: int, timeout_seconds: int = 600) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=5):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(5)
    raise HyperVLabError(f"Timed out waiting for {host}:{port} ({last_error})")


def wait_for_inventory_discovery(
    repo_root: Path,
    timeout_seconds: int = 900,
) -> dict[str, str]:
    deadline = time.time() + timeout_seconds
    inventory_path = repo_root / "inventories" / "lab" / "hosts.yml"
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            addresses = discover_vm_addresses()
            discovered = {address.inventory_host: address.ip_address for address in addresses}
            required_hosts = {"av-control-node", "av-repo-vm", "av-build-vm"}
            if required_hosts.issubset(discovered):
                update_inventory_hosts_file(inventory_path, addresses)
                return discovered
        except HyperVInventoryError as exc:
            last_error = exc
        time.sleep(10)
    raise HyperVLabError(f"Timed out discovering Hyper-V management IPs ({last_error})")


def deploy_from_control_node(
    repo_root: Path,
    private_key: Path,
    control_ip: str,
    repo_url: str = DEFAULT_REPO_URL,
    branch: str = DEFAULT_BRANCH,
    remote_repo_root: str = DEFAULT_REMOTE_REPO_ROOT,
) -> None:
    license_file = repo_root / "inventories" / "lab" / "group_vars" / "all" / "license_acceptance.yml"
    remote_license = f"{remote_repo_root}/inventories/lab/group_vars/all/license_acceptance.yml"
    public_key = private_key.with_suffix(".pub")
    upstream_iso = repo_root / "runtime" / "downloads" / "ubuntu-26.04-desktop-amd64.iso"
    remote_upstream_iso = f"{remote_repo_root}/runtime/downloads/{upstream_iso.name}"
    remote_repo_parent = str(PurePosixPath(remote_repo_root).parent)
    if not public_key.exists():
        raise HyperVLabError(f"SSH public key not found: {public_key}")

    remote_bootstrap = " && ".join(
        [
            f"sudo rm -rf {_remote_shell_quote(remote_repo_root)}",
            f"sudo mkdir -p {_remote_shell_quote(remote_repo_parent)}",
            f"sudo chown ziggi-py:ziggi-py {_remote_shell_quote(remote_repo_parent)}",
            f"git clone --branch {_remote_shell_quote(branch)} {_remote_shell_quote(repo_url)} {_remote_shell_quote(remote_repo_root)}",
            f"mkdir -p {_remote_shell_quote(f'{remote_repo_root}/runtime/downloads')}",
            f"mkdir -p {_remote_shell_quote(f'{remote_repo_root}/inventories/lab/group_vars/all')}",
            "mkdir -p ~/.ssh",
        ]
    )
    _run(_ssh_base(private_key) + [f"ziggi-py@{control_ip}", remote_bootstrap])

    _run(_scp_base(private_key) + [str(private_key), f"ziggi-py@{control_ip}:~/.ssh/ziggi-py-host-ed25519"])
    _run(_scp_base(private_key) + [str(public_key), f"ziggi-py@{control_ip}:~/.ssh/ziggi-py-host-ed25519.pub"])
    _run(_scp_base(private_key) + [str(license_file), f"ziggi-py@{control_ip}:{remote_license}"])
    _run(_scp_base(private_key) + [str(upstream_iso), f"ziggi-py@{control_ip}:{remote_upstream_iso}"])

    remote_deploy = " && ".join(
        [
            f"cd {_remote_shell_quote(remote_repo_root)}",
            "chmod 700 ~/.ssh",
            "chmod 600 ~/.ssh/ziggi-py-host-ed25519",
            "chmod 644 ~/.ssh/ziggi-py-host-ed25519.pub",
            "sudo cloud-init status --wait --long",
            "bash ./scripts/bootstrap-ansible.sh",
            "ansible-playbook -i inventories/lab/hosts.yml playbooks/control-node.yml",
            "ansible-playbook -i inventories/lab/hosts.yml playbooks/repo-vm.yml",
            "ansible-playbook -i inventories/lab/hosts.yml playbooks/build-vm.yml",
            "ansible-playbook -i inventories/lab/hosts.yml playbooks/build-pxe-client-assets.yml",
            "ansible-playbook -i inventories/lab/hosts.yml playbooks/healthcheck.yml",
        ]
    )
    _run(_ssh_base(private_key) + [f"ziggi-py@{control_ip}", remote_deploy])


def verify_pxe_reservation(private_key: Path, build_ip: str, timeout_seconds: int = 300) -> str:
    deadline = time.time() + timeout_seconds
    lease_path = "/var/lib/misc/dnsmasq.leases"
    expected = "192.168.50.184"
    while time.time() < deadline:
        result = _run(
            _ssh_base(private_key) + [f"ziggi-py@{build_ip}", f"sudo cat {lease_path}"],
            capture_output=True,
        )
        if expected in result.stdout:
            return result.stdout
        time.sleep(10)
    raise HyperVLabError(f"Timed out waiting for PXE client DHCP reservation {expected}.")


def write_summary(
    repo_root: Path,
    rotated: dict[str, str],
    seeds: dict[str, Path],
    discovered_ips: dict[str, str],
    lease_snapshot: str,
) -> Path:
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    summary_path = docs_dir / f"fresh-lab-rebuild-{now.strftime('%Y-%m-%d')}.md"
    lines = [
        f"# Fresh Lab Rebuild - {now.strftime('%B')} {now.day}, {now.strftime('%Y')}",
        "",
        "## Actions",
        "",
        "- Rotated the existing Hyper-V lab VMs by renaming them with an `.old.<timestamp>` suffix.",
        "- Rebuilt fresh `cidata` seed ISOs for `control-node`, `repo-vm`, and `build-vm`.",
        "- Created fresh Hyper-V VMs from the Ubuntu 26.04 cloud-image VHDX with fixed MAC addresses.",
        "- Brought the server VMs up on Hyper-V `Default Switch` DHCP, then rediscovered and rewrote the Ansible inventory from their fixed MAC addresses.",
        "- Deployed `control-node`, `repo-vm`, `build-vm`, PXE assets, and healthchecks from a clean clone on the control node.",
        "- Started a fresh `av-pxe-uefi-test-vm` and verified the reserved PXE lease.",
        "",
        "## Management IP Discovery",
        "",
    ]
    for host_name, ip_address in sorted(discovered_ips.items()):
        lines.append(f"- `{host_name}`: `{ip_address}`")
    lines.extend([
        "",
        "## Rotated VMs",
        "",
    ])
    for current_name, old_name in rotated.items():
        lines.append(f"- `{current_name}` -> `{old_name}`")
    lines.extend(["", "## Seed ISOs", ""])
    for seed_name, seed_path in seeds.items():
        lines.append(f"- `{seed_name}`: `{seed_path}`")
    lines.extend(["", "## PXE Lease Snapshot", "", "```text", lease_snapshot.rstrip(), "```", ""])
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Rotate and rebuild the local Hyper-V PXE lab from the repository.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--private-key", default=str(Path(__file__).resolve().parents[1] / ".local" / "ssh" / "ziggi-py-host-ed25519"))
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--skip-rotate", action="store_true")
    parser.add_argument("--skip-deploy", action="store_true")
    parser.add_argument("--active-root", default=str(DEFAULT_HYPERV_ROOT))
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    private_key = Path(args.private_key).resolve()
    active_root = Path(args.active_root).resolve()
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    validate_prerequisites(repo_root, private_key)
    ensure_switch()
    seeds = build_seed_isos(repo_root, run_id)
    all_vm_names = [spec.name for spec in SERVER_SPECS] + [PXE_TEST_SPEC.name]
    rotated = {} if args.skip_rotate else rotate_existing_vms(all_vm_names, active_root=active_root)
    create_fresh_vms(active_root, seeds)
    start_vms([spec.name for spec in SERVER_SPECS])

    discovered_ips = wait_for_inventory_discovery(repo_root)
    for host_name in ("av-control-node", "av-repo-vm", "av-build-vm"):
        wait_for_tcp(discovered_ips[host_name], 22, timeout_seconds=900)

    if not args.skip_deploy:
        deploy_from_control_node(
            repo_root,
            private_key,
            control_ip=discovered_ips["av-control-node"],
            repo_url=args.repo_url,
            branch=args.branch,
        )

    start_vms([PXE_TEST_SPEC.name])
    lease_snapshot = verify_pxe_reservation(private_key, build_ip=discovered_ips["av-build-vm"])
    summary_path = write_summary(repo_root, rotated, seeds, discovered_ips, lease_snapshot)
    print(f"Fresh lab rebuild summary written to: {summary_path}")


if __name__ == "__main__":
    main()
