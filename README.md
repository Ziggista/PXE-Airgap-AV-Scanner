# AV PXE Tooling

Python scaffolding for a three-part offline media scanning workflow with a primarily Ubuntu-based deployment model:

1. `proxy-server`: Ubuntu-hosted APT/mirror service with internet access.
2. `build-server`: Ubuntu-hosted PXE/build-side service that stages boot assets and talks to the repository service.
3. `pxe-client`: Ubuntu live client that boots into RAM for offline AV scanning and controlled file transfer.

Windows can still be used as an optional acquisition workstation for vendor media that is not naturally distributed through APT, but Items 1, 2, and 3 should all run on Ubuntu.

This repository now includes Ansible-managed control, proxy, and PXE server roles, plus a staged Ubuntu live-build workflow for the PXE client image. Physical PXE-client enforcement details such as post-boot NIC handling still need hardening and real hardware validation.

## Project layout

- `avtooling/`
  - `config.py`: shared config loading helpers.
  - `logging_utils.py`: consistent logging setup.
  - `media_acquisition.py`: optional workstation-side acquisition and staging helper.
  - `proxy_server.py`: fetch/cache HTTP service.
  - `pxe_build_server.py`: manifest/file service for PXE-side staging.
  - `client_workflow.py`: offline scan orchestration entrypoint.
- `tools/`
  - `acquire_media.py`
  - `bootstrap_local_machine.py`
  - `update_local_repo.py`
  - `start_proxy.py`
  - `start_build_server.py`
  - `run_scan_workflow.py`
- `configs/`
  - sample JSON configs for each role.
- `inventories/`, `playbooks/`, `roles/`
  - single Ansible repo for the whole platform.
- `autoinstall/`
  - Ubuntu autoinstall seed data for local control-node builds.
- `cloudinit/`
  - cloud-init seed data for Ubuntu cloud-image based control-node builds.
- `deploy/`
  - `systemd/`: service units for Ubuntu VMs.
- `docs/`
  - Hyper-V deployment notes.
  - APT repository governance for Item 1.
  - Ansible repository layout.
- `runtime/`
  - local cache, manifests, logs, and staged content.

## Quick start

Create a virtual environment and install the package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

Start the proxy server:

```bash
python ./tools/start_proxy.py --config ./configs/proxy.sample.json
```

Start the build server:

```bash
python ./tools/start_build_server.py --config ./configs/build-server.sample.json
```

Run a client-side scan workflow:

```bash
python ./tools/run_scan_workflow.py --config ./configs/client.sample.json
```

Acquire and stage non-APT media from a workstation if needed:

```bash
python ./tools/acquire_media.py --config ./configs/media-acquisition.sample.json
```

Bootstrap or re-sync the local Windows checkout from GitHub:

```powershell
python .\tools\bootstrap_local_machine.py
python .\tools\update_local_repo.py
```

## What this scaffold already does

- Supports an optional workstation acquisition/staging point for scanner binaries and boot media.
- Runs a simple HTTP fetch/cache service for approved upstream URLs.
- Lets the build server request staged artifacts through the proxy server.
- Serves manifests and files to downstream PXE-side consumers.
- Orchestrates multiple offline AV engine commands against a source path.
- Produces JSON scan reports and only copies files onward if all engines pass.
- Includes Ubuntu `systemd` unit templates for the VM-hosted services.
- Includes a single Ansible repository with inventories, playbooks, and role skeletons for all three platform components.
- Includes a control-node playbook path for the Ubuntu Ansible runner, including the `ziggi-py` automation user and guarded third-party repo handling.
- Includes a PXE client image role that stages an autologin desktop, disconnect banner, read-only source media mounts, gated writable destination mounts, and offline scan helpers.
- Includes a `build-pxe-client-assets.yml` playbook to sync ClamAV definitions from the proxy and publish PXE boot assets from the build VM.
- Includes a `sync-pxe-definitions.yml` playbook so daily ClamAV signature updates can flow proxy -> PXE server -> PXE client boot without rebuilding the full client image.

## What still needs implementation

- Final DHCP scope/interface tuning for the isolated PXE segment.
- Full PXE boot validation against real firmware or a dedicated PXE test VM.
- FAT/NTFS/exFAT validation inside the live environment.
- Network adapter teardown after boot.
- Robust hardware handling for USB destination media.
- Vendor-specific AV engine integrations and signature update handling.

## Design notes

- The proxy/build services are intended to run inside dedicated Ubuntu VMs on Hyper-V.
- The PXE client should boot an Ubuntu live runtime entirely into RAM, then mount source and destination media as needed.
- Windows may still be used to acquire vendor media, signatures, and portable scanners before publishing them to the build VM.
- The copy stage is blocked unless every enabled engine returns a success code.
- AV integrations are command-driven so you can plug in portable/offline scanners without rewriting the orchestration layer.
