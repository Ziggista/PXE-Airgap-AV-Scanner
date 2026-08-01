# Fresh Lab Rebuild Report (2026-08-01)

## Scope

This report captures the first full fresh-lab rebuild after rotating the previous Hyper-V lab VMs out of service and redeploying the environment from the Ansible repository.

## Rotated VMs

The previous lab VMs were shut down and renamed to preserve them as rollback points while freeing host resources:

- `av-control-node-26.old.20260801-030937`
- `av-repo-vm.old.20260801-030937`
- `av-build-vm.old.20260801-030937`
- `av-pxe-uefi-test-vm.old.20260801-030937`

All four rotated VMs were verified `Off`.

## Fresh VMs

Fresh VMs were recreated under `D:\AV\hyperv\active`:

- `av-control-node-26`
- `av-repo-vm`
- `av-build-vm`
- `av-pxe-uefi-test-vm`

Static management addressing and PXE reservation in the rebuilt lab:

- Control node: `172.23.23.27`
- Proxy/repo node: `172.23.27.229`
- PXE/build node: `172.23.30.254`
- PXE client DHCP reservation: `192.168.50.184`
- PXE client MAC: `00:15:5d:01:1c:0e`

The PXE test VM was rebuilt with `12 GB` assigned RAM for RAM-resident live-boot validation.

## Repo-Driven Deployment Path

The fresh control node was bootstrapped from the repo and then used as the Ansible control host:

1. Clone repo to `/opt/av-pxe-tooling`
2. Copy SSH automation keypair into `~/.ssh/`
3. Copy `inventories/lab/group_vars/all/license_acceptance.yml`
4. Copy upstream desktop ISO to `runtime/downloads/ubuntu-26.04-desktop-amd64.iso`
5. Run:

```bash
sudo cloud-init status --wait --long
bash ./scripts/bootstrap-ansible.sh
ansible-playbook -i inventories/lab/hosts.yml playbooks/control-node.yml
ansible-playbook -i inventories/lab/hosts.yml playbooks/repo-vm.yml
ansible-playbook -i inventories/lab/hosts.yml playbooks/build-vm.yml
ansible-playbook -i inventories/lab/hosts.yml playbooks/build-pxe-client-assets.yml
ansible-playbook -i inventories/lab/hosts.yml playbooks/healthcheck.yml
```

## Healthcheck Result

Fresh deployment healthcheck passed cleanly on all online nodes.

### Control node

- Host: `av-control-node`
- Repo HEAD: `9f4ec98`
- `cloud-init status`: `done`
- `ansible-playbook --version`: OK
- `git --version`: OK
- SSH service: `running`

### Proxy/repo node

- Host: `av-repo-vm`
- Nginx service: `running`
- Definitions endpoint: `http://172.23.27.229/definitions/clamav/`
- Artifacts endpoint: `http://172.23.27.229/artifacts/`
- Verified definition payloads present on disk:
  - `/srv/av-pxe/definitions/clamav/daily.cvd`
  - `/srv/av-pxe/definitions/clamav/main.cvd`

### PXE/build node

- Host: `av-build-vm`
- Services running:
  - `dnsmasq`
  - `nginx`
  - `tftpd_hpa`
  - `av_debug_collector`
- Proxy definition reachability: OK
- Active engine bundles staged in overlay:
  - `clamav`
  - `yara`
- Verified PXE artifacts:
  - `/srv/pxe/artifacts/ubuntu-26.04-av-client-test-amd64.iso`
  - `/srv/pxe/images/ubuntu-live-av-client-test/vmlinuz`
  - `/srv/pxe/images/ubuntu-live-av-client-test/initrd`
  - `/srv/tftp/boot.ipxe`
  - `/srv/tftp/snponly.efi`
  - `/srv/tftp/undionly.kpxe`

## Artifact Verification

The rebuilt build server contains:

- `/srv/pxe/artifacts/ubuntu-26.04-av-client-test-amd64.iso` (`3.5 GB`)
- `/srv/pxe/artifacts/ubuntu-26.04-desktop-amd64.iso` (`6.1 GB`)
- `/srv/pxe/images/ubuntu-live-av-client-test/vmlinuz` (`17 MB`)
- `/srv/pxe/images/ubuntu-live-av-client-test/initrd` (`92 MB`)

The PXE client image build now detects the live squashfs dynamically instead of assuming `minimal.standard.live.squashfs`.

## PXE Reservation Verification

After starting the fresh PXE test VM, the build server lease file confirmed the expected reserved lease:

```text
00:15:5d:01:1c:0e -> 192.168.50.184
```

The build node neighbor table also showed the PXE client reachable on the isolated PXE network.

## Rebuildability Fixes Landed

The fresh rebuild validated these repo-driven fixes:

- Per-run seed ISO generation to avoid stale Hyper-V media locks
- Static first-boot management networking through cloud-init `network-config`
- Automatic removal of cloud-init DHCP netplan after Ansible applies managed netplan
- Fixed-memory Hyper-V handling in the rebuild helper
- Explicit wait for cloud-init completion before Ansible bootstrap
- Bootstrap execution through `bash` on the control node
- Automatic SSH key seeding onto the fresh control node
- Automatic staging of the upstream desktop ISO into the build workflow
- Dynamic live squashfs discovery during PXE client image creation
- DHCP reservation for the PXE client MAC

## Remaining Notes

- The rotated `.old` VMs remain available as offline rollback points.
- The fresh PXE test VM successfully reached the PXE network and obtained the reserved lease; this report does not replace GUI-level validation of the full client desktop workflow.
- The fresh lab is now in a state where the online servers are rebuildable from the repo and the PXE client path can be exercised from the rebuilt infrastructure.
