# Control Node Operations

The Ubuntu control node is the only machine in this stack that should have broad internet access by default.

## Repo policy

- Official Ubuntu repositories are allowed by default.
- Third-party apt repositories are blocked by default in Ansible.
- If a third-party repository is needed, review it first and then set:
  - `control_node_allow_third_party_repos: true`
  - `control_node_extra_apt_repositories: [...]`

This keeps general package access simple while forcing explicit review for non-Ubuntu package sources.

## Automation user

The control node automation user is `ziggi-py`.

Expected properties:

- SSH key login
- `sudo` without password
- used for Python-based local bootstrap and Ansible-driven administration

The tracked public key is defined in [inventories/lab/group_vars/control_node.yml](C:/Users/Ziggi/AV/inventories/lab/group_vars/control_node.yml). The corresponding private key is kept locally under the gitignored `.local/ssh/` folder as `ziggi-py-host-ed25519`.

## Local Windows bootstrap

From a Windows workstation with Python and Git installed:

```powershell
python .\tools\bootstrap_local_machine.py
```

This will:

- clone or refresh the GitHub repository
- create `.local\ssh\ziggi-py-ed25519`
- create `.local\venv`
- install the local helper dependencies needed for repo maintenance

To re-sync later:

```powershell
python .\tools\update_local_repo.py
```

## Hyper-V inventory refresh

The preferred lab path now seeds the control, proxy, and build VMs with static management addresses from first boot by shipping `network-config` in the cloud-init ISO.

Expected management addresses:

- `av-control-node`: `172.23.23.27`
- `av-repo-vm`: `172.23.27.229`
- `av-build-vm`: `172.23.30.254`

If an older lab instance was created before that static seed support existed, or if a VM was rebuilt outside the tracked workflow, use the inventory refresh helper to discover the current Hyper-V `Default Switch` address and patch [inventories/lab/hosts.yml](C:/Users/Ziggi/AV/inventories/lab/hosts.yml):

Use the local helper before Ansible runs if a lab VM becomes unreachable:

```powershell
python .\tools\refresh_hyperv_inventory.py --check
python .\tools\refresh_hyperv_inventory.py
```

## Full lab rebuild

For a clean Hyper-V rebuild from the tracked repo, use:

```powershell
python .\tools\rebuild_hyperv_lab.py
```

This workflow:

- rotates the existing lab VMs by renaming them with an `.old.<timestamp>` suffix
- rebuilds the `cidata` seed ISOs for `control-node`, `repo-vm`, and `build-vm`
- recreates fresh Hyper-V VMs with fixed MAC addresses and static first-boot management networking
- copies the local automation SSH keypair into the fresh control node so Ansible can reach the proxy and build guests
- deploys the control node, proxy node, PXE build node, PXE assets, and healthchecks from a clean clone on the control node
- starts a fresh `av-pxe-uefi-test-vm` and verifies that the PXE DHCP reservation stays on `192.168.50.184`
