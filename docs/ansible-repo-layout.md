# Ansible Repository Layout

This project now includes a single Ansible repository for the whole platform.

## Structure

- `ansible.cfg`
- `inventories/lab/`
- `playbooks/`
- `roles/`
- `collections/requirements.yml`
- `scripts/bootstrap-ansible.sh`

## Intended usage

Run Ansible from the Ubuntu control node, not from native Windows.

Typical flow:

```bash
git clone <repo> /opt/av-pxe-tooling
cd /opt/av-pxe-tooling
./scripts/bootstrap-ansible.sh
ansible-playbook playbooks/site.yml
```

Use the playbooks individually during development:

```bash
ansible-playbook playbooks/repo-vm.yml
ansible-playbook playbooks/build-vm.yml
ansible-playbook playbooks/pxe-client-image.yml
```

Control-node preparation is handled separately:

```bash
ansible-playbook playbooks/control-node.yml
```

## Notes

- The tracked lab inventory now expects fixed management addresses and fixed Hyper-V MAC assignments for the control, proxy, and build VMs.
- The `control_node` path assumes the control node can reach official Ubuntu repositories on the internet.
- Non-Ubuntu apt repositories are blocked by default and must be explicitly approved by setting `control_node_allow_third_party_repos: true` and populating `control_node_extra_apt_repositories`.
- The `repo_vm` role sets up the basis for an `aptly` + `nginx` repository VM.
- The `build_vm` role sets up the basis for a PXE/TFTP build VM.
- The `pxe_client_image` role currently prepares packages and wrapper scripts, not a complete bootable live image.

## Windows-side orchestration

The repo also carries the Hyper-V orchestration helper used to rotate the existing lab and stand up a fresh control/proxy/build/PXE-test set:

```powershell
python .\tools\rebuild_hyperv_lab.py
```

This is the preferred rebuildability path for the local Windows lab.
