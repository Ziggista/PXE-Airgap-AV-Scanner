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
5. Waits for DHCP management discovery and SSH on the fresh control, proxy, and build VMs.
6. Copies the local automation SSH keypair into `~/.ssh/` on the fresh control node.
7. Copies the local operator-managed `license_acceptance.yml`, the committed base inventory, and the generated DHCP overlay inventory into a clean repo clone on the control node.
8. Runs:
   - `ansible-playbook -i inventories/lab/hosts.yml -i runtime/generated/hyperv-dhcp-hosts.yml playbooks/control-node.yml`
   - `ansible-playbook -i inventories/lab/hosts.yml -i runtime/generated/hyperv-dhcp-hosts.yml playbooks/repo-vm.yml`
   - `ansible-playbook -i inventories/lab/hosts.yml -i runtime/generated/hyperv-dhcp-hosts.yml playbooks/build-vm.yml`
   - `ansible-playbook -i inventories/lab/hosts.yml -i runtime/generated/hyperv-dhcp-hosts.yml playbooks/build-pxe-client-assets.yml`
   - `ansible-playbook -i inventories/lab/hosts.yml -i runtime/generated/hyperv-dhcp-hosts.yml playbooks/healthcheck.yml`
9. Verifies build-node checkpoints before PXE test:
   - `dnsmasq`, `nginx`, `tftpd-hpa`, and `av-debug-collector` are active
   - `/boot.ipxe`, `vmlinuz`, `initrd`, and the client ISO return `200`
   - the published asset files exist and have content
10. Starts a fresh `av-pxe-uefi-test-vm`.
11. Verifies that the PXE client reservation appears on `192.168.50.184`.
12. Verifies nginx access logs show the PXE client fetched:
   - `/boot.ipxe`
   - `/images/ubuntu-live-av-client-test/vmlinuz`
   - `/images/ubuntu-live-av-client-test/initrd`
   - `/artifacts/ubuntu-26.04-av-client-test-amd64.iso`

## Important prerequisites

- [inventories/lab/group_vars/all/license_acceptance.yml.example](C:/Users/Ziggi/AV/inventories/lab/group_vars/all/license_acceptance.yml.example) must have been copied locally to `inventories/lab/group_vars/all/license_acceptance.yml`.
- The local SSH private key must exist at `.local/ssh/ziggi-py-host-ed25519`.
- The Ubuntu base cloud image VHDX must exist at `D:\AV\cloud-images\ubuntu-26.04-server-cloudimg-amd64.vhdx`.
- Hyper-V must already be available on the Windows host.

## Expected fresh-state addresses

- `av-control-node`: current Hyper-V `Default Switch` DHCP lease discovered from fixed MAC `00:15:5d:01:1c:08`
- `av-repo-vm`: current Hyper-V `Default Switch` DHCP lease discovered from fixed MAC `00:15:5d:01:1c:09`
- `av-build-vm`: current Hyper-V `Default Switch` DHCP lease discovered from fixed MAC `00:15:5d:01:1c:0a`
- `av-build-vm` PXE side: `192.168.50.2`
- `av-pxe-client` reserved PXE lease: `192.168.50.184`

## DHCP overlay artifact

- Base inventory: [inventories/lab/hosts.yml](C:/Users/Ziggi/AV/inventories/lab/hosts.yml)
- Generated overlay: `runtime/generated/hyperv-dhcp-hosts.yml`
- Refresh command:

```powershell
python .\tools\refresh_hyperv_inventory.py
```
