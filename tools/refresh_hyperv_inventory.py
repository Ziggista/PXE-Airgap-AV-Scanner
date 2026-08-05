from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from avtooling.hyperv_inventory import (  # noqa: E402
    HyperVInventoryError,
    discover_vm_addresses,
    write_inventory_overlay,
)
def default_overlay_path() -> Path:
    return Path(__file__).resolve().parents[1] / "runtime" / "generated" / "hyperv-dhcp-hosts.yml"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve Hyper-V guest IPs after reboot and optionally update the Ansible lab inventory."
    )
    parser.add_argument(
        "--overlay-out",
        default=str(default_overlay_path()),
        help="Path to the generated DHCP overlay inventory file.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only print discovered IPs. Do not modify the generated overlay file.",
    )
    args = parser.parse_args()

    overlay_path = Path(args.overlay_out).resolve()

    try:
        addresses = discover_vm_addresses()
        changed = False if args.check else write_inventory_overlay(overlay_path, addresses)
    except HyperVInventoryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    for address in addresses:
        print(
            f"{address.inventory_host}: {address.ip_address} "
            f"(vm={address.vm_name}, mac={address.mac_address}, switch={address.switch_name}, state={address.neighbor_state})"
        )

    if args.check:
        print(f"Overlay left unchanged: {overlay_path}")
    else:
        status = "updated" if changed else "already current"
        print(f"Overlay {status}: {overlay_path}")


if __name__ == "__main__":
    main()
