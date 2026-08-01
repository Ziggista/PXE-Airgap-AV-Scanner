from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from avtooling.hyperv_inventory import (  # noqa: E402
    HyperVInventoryError,
    discover_vm_addresses,
    update_inventory_hosts_file,
)


def default_inventory_path() -> Path:
    return Path(__file__).resolve().parents[1] / "inventories" / "lab" / "hosts.yml"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve Hyper-V guest IPs after reboot and optionally update the Ansible lab inventory."
    )
    parser.add_argument(
        "--inventory",
        default=str(default_inventory_path()),
        help="Path to the Ansible hosts.yml inventory file.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only print discovered IPs. Do not modify the inventory file.",
    )
    args = parser.parse_args()

    inventory_path = Path(args.inventory).resolve()

    try:
        addresses = discover_vm_addresses()
        changed = False if args.check else update_inventory_hosts_file(inventory_path, addresses)
    except HyperVInventoryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    for address in addresses:
        print(
            f"{address.inventory_host}: {address.ip_address} "
            f"(vm={address.vm_name}, mac={address.mac_address}, switch={address.switch_name}, state={address.neighbor_state})"
        )

    if args.check:
        print(f"Inventory left unchanged: {inventory_path}")
    else:
        status = "updated" if changed else "already current"
        print(f"Inventory {status}: {inventory_path}")


if __name__ == "__main__":
    main()
