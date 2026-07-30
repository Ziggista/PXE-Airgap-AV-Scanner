# Ubuntu Control Node Build

This project includes both an Ubuntu autoinstall seed and a cloud-init seed for the local Hyper-V control node VM.

## Seed location

- `autoinstall/control-node/user-data`
- `autoinstall/control-node/meta-data`
- `cloudinit/control-node/user-data`
- `cloudinit/control-node/meta-data`

## Windows ISO build

For cloud-image based boots on Hyper-V, build the `cidata` ISO with the Python helper instead of the default Windows IMAPI path. The IMAPI-generated image can truncate filenames to 8.3 names, which breaks cloud-init discovery.

```powershell
C:\Users\Ziggi\AppData\Local\Python\pythoncore-3.14-64\python.exe `
  -m pip install --target C:\Users\Ziggi\AV\runtime\pydeps pycdlib

$env:PYTHONPATH='C:\Users\Ziggi\AV;C:\Users\Ziggi\AV\runtime\pydeps'
C:\Users\Ziggi\AppData\Local\Python\pythoncore-3.14-64\python.exe `
  C:\Users\Ziggi\AV\tools\build_cloudinit_iso.py `
  --source-dir C:\Users\Ziggi\AV\cloudinit\control-node `
  --output-iso D:\AV\cloudinit\control-node-seed.iso
```

## Current assumptions

- Ubuntu 26.04 LTS cloud image
- Hyper-V Generation 2 VM
- VM storage on `D:\AV`
- cloud-init seed delivered by attached `cidata` ISO

## Installed baseline

The seed currently installs:

- `ansible-core`
- `git`
- `python3-venv`
- `qemu-guest-agent`
- `rsync`
- `curl`

## Current login

The seeded build currently uses:

- username: `ziggi-ubuntu`
- password: defined in [cloudinit/control-node/user-data](C:/Users/Ziggi/AV/cloudinit/control-node/user-data)

Rotate the seeded password immediately after the install completes.

## Reference

- Full host-side command history and rebuild steps: [docs/control-node-build-runbook.md](C:/Users/Ziggi/AV/docs/control-node-build-runbook.md)
