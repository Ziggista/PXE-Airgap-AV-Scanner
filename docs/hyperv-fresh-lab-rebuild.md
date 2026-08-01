# Hyper-V Fresh Lab Rebuild

This document describes the tracked Windows-side entry point for rebuilding the local Hyper-V lab from the repository.

## Entry point

Run:

```powershell
python .\tools\rebuild_hyperv_lab.py
```

## What it does

1. Stops the current lab VMs and renames them with an `.old.<timestamp>` suffix.
2. Rebuilds `cidata` seed ISOs from:
   - [cloudinit/control-node](C:/Users/Ziggi/AV/cloudinit/control-node)
   - [cloudinit/repo-vm](C:/Users/Ziggi/AV/cloudinit/repo-vm)
   - [cloudinit/build-vm](C:/Users/Ziggi/AV/cloudinit/build-vm)
3. Recreates fresh Hyper-V VMs from the Ubuntu 26.04 cloud-image VHDX.
4. Uses fixed Hyper-V MAC addresses that match:
   - [inventories/lab/hosts.yml](C:/Users/Ziggi/AV/inventories/lab/hosts.yml)
   - the cloud-init `network-config` files
5. Waits for SSH on the fresh control, proxy, and build VMs.
6. Copies the local operator-managed `license_acceptance.yml` into a clean repo clone on the control node.
7. Runs:
   - `playbooks/control-node.yml`
   - `playbooks/repo-vm.yml`
   - `playbooks/build-vm.yml`
   - `playbooks/build-pxe-client-assets.yml`
   - `playbooks/healthcheck.yml`
8. Starts a fresh `av-pxe-uefi-test-vm`.
9. Verifies that the PXE client reservation appears on `192.168.50.184`.

## Important prerequisites

- [inventories/lab/group_vars/all/license_acceptance.yml.example](C:/Users/Ziggi/AV/inventories/lab/group_vars/all/license_acceptance.yml.example) must have been copied locally to `inventories/lab/group_vars/all/license_acceptance.yml`.
- The local SSH private key must exist at `.local/ssh/ziggi-py-host-ed25519`.
- The Ubuntu base cloud image VHDX must exist at `D:\AV\cloud-images\ubuntu-26.04-server-cloudimg-amd64.vhdx`.
- Hyper-V must already be available on the Windows host.

## Expected fresh-state addresses

- `av-control-node`: `172.23.23.27`
- `av-repo-vm`: `172.23.27.229`
- `av-build-vm`: `172.23.30.254`
- `av-pxe-client` reserved PXE lease: `192.168.50.184`
