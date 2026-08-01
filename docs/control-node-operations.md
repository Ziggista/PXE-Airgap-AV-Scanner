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

The lab inventory uses Hyper-V `Default Switch` addresses for the control, proxy, and build VMs. Those management IPs can change after a guest reboot, host reboot, or storage move.

Use the local helper before Ansible runs if a lab VM becomes unreachable:

```powershell
python .\tools\refresh_hyperv_inventory.py --check
python .\tools\refresh_hyperv_inventory.py
```

As of Friday, July 31, 2026, the build VM moved from `172.23.25.109` to `172.23.30.254` after a restart following its VHDX relocation from `D:` to `C:`.
