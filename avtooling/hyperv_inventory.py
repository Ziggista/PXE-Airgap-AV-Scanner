from __future__ import annotations

import ipaddress
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


DEFAULT_VM_HOST_MAP = {
    "av-control-node-26": "av-control-node",
    "av-repo-vm": "av-repo-vm",
    "av-build-vm": "av-build-vm",
}

DEFAULT_PREFERRED_SWITCH_BY_HOST = {
    "av-control-node": "Default Switch",
    "av-repo-vm": "Default Switch",
    "av-build-vm": "Default Switch",
}


@dataclass(frozen=True)
class VmAddress:
    vm_name: str
    inventory_host: str
    ip_address: str
    mac_address: str
    switch_name: str
    neighbor_state: str


class HyperVInventoryError(RuntimeError):
    pass


def _run_powershell_json(script: str) -> list[dict[str, object]]:
    command = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        if "Access denied" in stderr:
            raise HyperVInventoryError(
                "Hyper-V query failed with access denied. Run this script in an elevated PowerShell session "
                "or as a user with Hyper-V administrative access."
            )
        raise HyperVInventoryError(f"PowerShell query failed: {stderr}")

    payload = result.stdout.strip()
    if not payload:
        return []

    parsed = json.loads(payload)
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return parsed
    raise HyperVInventoryError("Unexpected PowerShell JSON payload.")


def _normalize_mac(mac: str) -> str:
    collapsed = re.sub(r"[^0-9A-Fa-f]", "", mac).upper()
    if len(collapsed) != 12:
        raise HyperVInventoryError(f"Unexpected MAC address format: {mac}")
    return "-".join(collapsed[index : index + 2] for index in range(0, 12, 2))


def _state_rank(state: str) -> int:
    order = {
        "Reachable": 0,
        "Permanent": 1,
        "Probe": 2,
        "Delay": 3,
        "Stale": 4,
    }
    return order.get(state, 99)


def _switch_rank(inventory_host: str, switch_name: str) -> int:
    preferred = DEFAULT_PREFERRED_SWITCH_BY_HOST.get(inventory_host)
    if preferred and switch_name == preferred:
        return 0
    if switch_name == "Default Switch":
        return 1
    return 10


def _is_candidate_ipv4(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return (
        isinstance(ip, ipaddress.IPv4Address)
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and str(ip) != "0.0.0.0"
    )


def discover_vm_addresses(vm_host_map: dict[str, str] | None = None) -> list[VmAddress]:
    vm_host_map = vm_host_map or DEFAULT_VM_HOST_MAP
    vm_names = list(vm_host_map)
    vm_names_literal = ",".join(f"'{name}'" for name in vm_names)

    adapter_script = rf"""
$ErrorActionPreference = 'Stop'
$adapters = Get-VMNetworkAdapter -VMName {vm_names_literal} |
  Select-Object VMName,SwitchName,MacAddress
$adapters | ConvertTo-Json -Depth 4
"""
    neighbor_script = r"""
$ErrorActionPreference = 'Stop'
$neighbors = Get-NetNeighbor -AddressFamily IPv4 |
  Select-Object IPAddress,LinkLayerAddress,@{Name='State';Expression={$_.State.ToString()}},ifIndex
$neighbors | ConvertTo-Json -Depth 4
"""

    adapters = _run_powershell_json(adapter_script)
    neighbors = _run_powershell_json(neighbor_script)

    neighbor_by_mac: dict[str, list[dict[str, object]]] = {}
    for neighbor in neighbors:
        raw_mac = str(neighbor.get("LinkLayerAddress", "")).strip()
        if not raw_mac or raw_mac == "00-00-00-00-00-00":
            continue
        if not _is_candidate_ipv4(str(neighbor.get("IPAddress", ""))):
            continue
        normalized_mac = _normalize_mac(raw_mac)
        neighbor_by_mac.setdefault(normalized_mac, []).append(neighbor)

    discovered: list[VmAddress] = []

    for adapter in adapters:
        vm_name = str(adapter.get("VMName", ""))
        inventory_host = vm_host_map.get(vm_name)
        if not inventory_host:
            continue
        normalized_mac = _normalize_mac(str(adapter.get("MacAddress", "")))
        candidates = neighbor_by_mac.get(normalized_mac, [])
        if not candidates:
            continue

        best = sorted(
            candidates,
            key=lambda item: (
                _state_rank(str(item.get("State", ""))),
                str(item.get("IPAddress", "")),
            ),
        )[0]
        discovered.append(
            VmAddress(
                vm_name=vm_name,
                inventory_host=inventory_host,
                ip_address=str(best["IPAddress"]),
                mac_address=normalized_mac,
                switch_name=str(adapter.get("SwitchName", "")),
                neighbor_state=str(best.get("State", "")),
            )
        )

    discovered_vm_names = {address.vm_name for address in discovered}
    missing = sorted(vm_name for vm_name in vm_names if vm_name not in discovered_vm_names)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise HyperVInventoryError(
            "Could not resolve current IPv4 addresses for: "
            f"{missing_text}. Ensure the VMs are running and have spoken on the network, then retry."
        )

    primary_by_host: dict[str, VmAddress] = {}
    for address in discovered:
        existing = primary_by_host.get(address.inventory_host)
        if existing is None:
            primary_by_host[address.inventory_host] = address
            continue
        current_key = (
            _switch_rank(address.inventory_host, address.switch_name),
            _state_rank(address.neighbor_state),
            address.ip_address,
        )
        existing_key = (
            _switch_rank(existing.inventory_host, existing.switch_name),
            _state_rank(existing.neighbor_state),
            existing.ip_address,
        )
        if current_key < existing_key:
            primary_by_host[address.inventory_host] = address

    return sorted(primary_by_host.values(), key=lambda item: item.inventory_host)


def update_inventory_hosts_file(path: Path, addresses: list[VmAddress]) -> bool:
    content = path.read_text(encoding="utf-8")
    updated = content
    changed = False

    for address in addresses:
        pattern = (
            rf"(^\s+{re.escape(address.inventory_host)}:\s*\r?\n"
            rf"(?:^\s+.*\r?\n)*?"
            rf"^\s+ansible_host:\s*)([0-9.]+)"
        )
        replacement = rf"\g<1>{address.ip_address}"
        updated, replacements = re.subn(pattern, replacement, updated, count=1, flags=re.MULTILINE)
        if replacements != 1:
            raise HyperVInventoryError(
                f"Could not find ansible_host entry for inventory host '{address.inventory_host}' in {path}."
            )
        changed = changed or (updated != content)
        content = updated

    if changed:
        path.write_text(updated, encoding="utf-8")
    return changed


def render_inventory_overlay(addresses: list[VmAddress]) -> str:
    grouped = {
        "av-control-node": "control_node",
        "av-repo-vm": "repo_vm",
        "av-build-vm": "build_vm",
    }
    lines = ["all:", "  children:"]
    for address in sorted(addresses, key=lambda item: item.inventory_host):
        group = grouped.get(address.inventory_host)
        if not group:
            continue
        lines.extend(
            [
                f"    {group}:",
                "      hosts:",
                f"        {address.inventory_host}:",
                f"          ansible_host: {address.ip_address}",
            ]
        )
    return "\n".join(lines) + "\n"


def write_inventory_overlay(path: Path, addresses: list[VmAddress]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_inventory_overlay(addresses)
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == rendered:
        return False
    path.write_text(rendered, encoding="utf-8")
    return True
