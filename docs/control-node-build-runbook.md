# Control Node Build Runbook

This runbook captures the Windows-side commands and tooling used to get the local Ubuntu control node working on Hyper-V as of July 30, 2026.

## Outcome

Working state reached:

- VM name: `av-control-node-26`
- guest hostname: `av-control-node`
- switch: `Default Switch`
- base disk: `D:\AV\cloud-images\ubuntu-26.04-server-cloudimg-amd64.vhdx`
- seed ISO: `D:\AV\cloudinit\control-node-seed.iso`
- current cloud-init source: `DataSourceNoCloud [seed=/dev/sr0]`
- login user: `ziggi-ubuntu`
- password location: set locally in [cloudinit/control-node/user-data](C:/Users/Ziggi/AV/cloudinit/control-node/user-data) before build

## Important findings

1. The Ubuntu 26.04 cloud image file downloaded locally was `qcow2`, not raw.
2. Hyper-V booted correctly after converting that image to `vhdx` with `qemu-img`.
3. A Windows IMAPI-built seed ISO was not usable because it exposed short 8.3 filenames like `METADA~1` and `USERDA~1`.
4. cloud-init only started working reliably after rebuilding the seed ISO with exact `meta-data` and `user-data` names.
5. The cloud-init user schema needed to be corrected before the intended local user and password worked.

## Paths used

```text
Workspace: C:\Users\Ziggi\AV
Python:    C:\Users\Ziggi\AppData\Local\Python\pythoncore-3.14-64\python.exe
qemu-img:  C:\Users\Ziggi\AV\qemu-img-win-x64-2_3_0\qemu-img.exe
VM root:   D:\AV\hyperv
Images:    D:\AV\cloud-images
Seed ISO:  D:\AV\cloudinit\control-node-seed.iso
```

## 1. Verify Hyper-V

These were the baseline checks on the host:

```powershell
Get-VMHost
Get-VMSwitch
```

## 2. Download the Ubuntu media

The repo already contains acquisition tooling and downloaded media under `runtime/downloads/`. The resulting local cloud image used for the control node was:

```text
C:\Users\Ziggi\AV\runtime\downloads\ubuntu-26.04-server-cloudimg-amd64.img
```

The important follow-up check was confirming the format:

```powershell
C:\Users\Ziggi\AV\qemu-img-win-x64-2_3_0\qemu-img.exe info `
  C:\Users\Ziggi\AV\runtime\downloads\ubuntu-26.04-server-cloudimg-amd64.img
```

Expected result:

```text
file format: qcow2
```

## 3. Convert the cloud image for Hyper-V

The working conversion command was:

```powershell
C:\Users\Ziggi\AV\qemu-img-win-x64-2_3_0\qemu-img.exe convert -p -f qcow2 -O vhdx `
  C:\Users\Ziggi\AV\runtime\downloads\ubuntu-26.04-server-cloudimg-amd64.img `
  D:\AV\cloud-images\ubuntu-26.04-server-cloudimg-amd64.vhdx
```

Optional verification:

```powershell
C:\Users\Ziggi\AV\qemu-img-win-x64-2_3_0\qemu-img.exe info `
  D:\AV\cloud-images\ubuntu-26.04-server-cloudimg-amd64.vhdx
```

## 4. Prepare the cloud-init seed

The working seed files are:

- [cloudinit/control-node/meta-data](C:/Users/Ziggi/AV/cloudinit/control-node/meta-data)
- [cloudinit/control-node/user-data](C:/Users/Ziggi/AV/cloudinit/control-node/user-data)

The final `meta-data` values used were:

```yaml
instance-id: av-control-node-cloudimg-20260730b
local-hostname: av-control-node
```

## 5. Install the ISO builder dependency

The local helper uses `pycdlib` and was installed into the workspace rather than system-wide:

```powershell
C:\Users\Ziggi\AppData\Local\Python\pythoncore-3.14-64\python.exe `
  -m pip install --target C:\Users\Ziggi\AV\runtime\pydeps pycdlib
```

## 6. Build the working `cidata` ISO

This is the command that produced the working seed ISO with exact filenames:

```powershell
$env:PYTHONPATH='C:\Users\Ziggi\AV;C:\Users\Ziggi\AV\runtime\pydeps'
C:\Users\Ziggi\AppData\Local\Python\pythoncore-3.14-64\python.exe `
  C:\Users\Ziggi\AV\tools\build_cloudinit_iso.py `
  --source-dir C:\Users\Ziggi\AV\cloudinit\control-node `
  --output-iso D:\AV\cloudinit\control-node-seed.iso
```

Verify the ISO contents on Windows:

```powershell
$img = Mount-DiskImage -ImagePath 'D:\AV\cloudinit\control-node-seed.iso' -PassThru
$vol = $img | Get-Volume
$drive = $vol.DriveLetter + ':'
Get-ChildItem $drive -Force | Select-Object Name,Length
Dismount-DiskImage -ImagePath 'D:\AV\cloudinit\control-node-seed.iso'
```

Expected filenames:

```text
meta-data
user-data
```

## 7. Recreate the Hyper-V VM cleanly

When cloud-init content changed, the VM had to be recreated from the clean base VHDX so first boot would rerun with a fresh instance.

```powershell
$ErrorActionPreference='Stop'
$vmName = 'av-control-node-26'
$vmRoot = 'D:\AV\hyperv\' + $vmName
$vmPath = Join-Path $vmRoot $vmName
$baseVhdx = 'D:\AV\cloud-images\ubuntu-26.04-server-cloudimg-amd64.vhdx'
$vmVhdx = Join-Path $vmRoot ($vmName + '.vhdx')
$seedIso = 'D:\AV\cloudinit\control-node-seed.iso'

if (Get-VM -Name $vmName -ErrorAction SilentlyContinue) {
  Stop-VM -Name $vmName -TurnOff -Force -ErrorAction SilentlyContinue | Out-Null
  Remove-VM -Name $vmName -Force
}

if (Test-Path $vmRoot) {
  Remove-Item -LiteralPath $vmRoot -Recurse -Force
}

New-Item -ItemType Directory -Path $vmRoot -Force | Out-Null
Copy-Item -LiteralPath $baseVhdx -Destination $vmVhdx -Force
Resize-VHD -Path $vmVhdx -SizeBytes 32GB

New-VM -Name $vmName -Generation 2 -MemoryStartupBytes 4GB `
  -VHDPath $vmVhdx -Path $vmPath -SwitchName 'Default Switch' | Out-Null

Set-VMProcessor -VMName $vmName -Count 2
Set-VMMemory -VMName $vmName -DynamicMemoryEnabled $true `
  -MinimumBytes 2GB -StartupBytes 4GB -MaximumBytes 8GB
Set-VM -Name $vmName -AutomaticCheckpointsEnabled $false
Set-VMFirmware -VMName $vmName -EnableSecureBoot On `
  -SecureBootTemplate 'MicrosoftUEFICertificateAuthority'

Add-VMDvdDrive -VMName $vmName -Path $seedIso | Out-Null
$hdd = Get-VMHardDiskDrive -VMName $vmName | Select-Object -First 1
Set-VMFirmware -VMName $vmName -FirstBootDevice $hdd
Start-VM -Name $vmName | Out-Null
```

## 8. Find the guest IP on `Default Switch`

This was the reliable host-side lookup:

```powershell
$mac = ((Get-VMNetworkAdapter -VMName 'av-control-node-26').MacAddress -replace '(..)', '$1-').TrimEnd('-')
Get-NetNeighbor -AddressFamily IPv4 |
  Where-Object { $_.LinkLayerAddress -eq $mac } |
  Select-Object IPAddress,LinkLayerAddress,State
```

## 9. Verify SSH is listening

```powershell
Test-NetConnection -ComputerName 172.31.116.115 -Port 22
```

Replace the IP with the current neighbor-table result.

## 10. Install SSH verification tooling on Windows

`paramiko` was installed into the workspace to verify the guest non-interactively:

```powershell
C:\Users\Ziggi\AppData\Local\Python\pythoncore-3.14-64\python.exe `
  -m pip install --target C:\Users\Ziggi\AV\runtime\pydeps paramiko
```

## 11. Verify login and cloud-init from Windows

This inline Python pattern was used successfully:

```powershell
@'
import sys
sys.path.insert(0, r'C:\Users\Ziggi\AV\runtime\pydeps')
import paramiko

host = '172.31.116.115'
user = 'ziggi-ubuntu'
password = 'read from cloudinit/control-node/user-data'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(
    hostname=host,
    username=user,
    password=password,
    timeout=20,
    banner_timeout=20,
    auth_timeout=20,
    look_for_keys=False,
    allow_agent=False,
)

for cmd in [
    'hostnamectl --static || hostname',
    'id',
    'cloud-init status --long || true',
]:
    stdin, stdout, stderr = client.exec_command(cmd)
    print('=== CMD ===')
    print(cmd)
    print(stdout.read().decode('utf-8', 'replace'))
    err = stderr.read().decode('utf-8', 'replace')
    if err:
        print('--- STDERR ---')
        print(err)

client.close()
'@ | C:\Users\Ziggi\AppData\Local\Python\pythoncore-3.14-64\python.exe -
```

Successful results included:

- hostname: `av-control-node`
- user id output for `ziggi-ubuntu`
- cloud-init datasource: `DataSourceNoCloud [seed=/dev/sr0]`

## 12. Wait for cloud-init completion

This was the verification pattern used after first boot:

```powershell
@'
import sys
sys.path.insert(0, r'C:\Users\Ziggi\AV\runtime\pydeps')
import paramiko

host = '172.31.116.115'
user = 'ziggi-ubuntu'
password = 'read from cloudinit/control-node/user-data'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(
    hostname=host,
    username=user,
    password=password,
    timeout=20,
    banner_timeout=20,
    auth_timeout=20,
    look_for_keys=False,
    allow_agent=False,
)

stdin, stdout, stderr = client.exec_command('cloud-init status --wait --long')
print(stdout.read().decode('utf-8', 'replace'))
print(stderr.read().decode('utf-8', 'replace'))

client.close()
'@ | C:\Users\Ziggi\AppData\Local\Python\pythoncore-3.14-64\python.exe -
```

Expected end state:

```text
status: done
detail: DataSourceNoCloud [seed=/dev/sr0]
```

## 13. Post-build guest checks

These commands were used to confirm the control node was usable:

```bash
ansible --version | head -n 1
git --version
python3 --version
systemctl is-active ssh
systemctl is-active qemu-guest-agent
```

Verified working:

- `ansible [core 2.20.1]`
- `git version 2.53.0`
- `Python 3.14.4`
- `ssh` was `active`

Known issue:

- `qemu-guest-agent` is installed but its service remained `inactive` and needs separate follow-up.

## Files added to support the working build

- [avtooling/cloudinit_iso.py](C:/Users/Ziggi/AV/avtooling/cloudinit_iso.py)
- [tools/build_cloudinit_iso.py](C:/Users/Ziggi/AV/tools/build_cloudinit_iso.py)
- [cloudinit/control-node/user-data](C:/Users/Ziggi/AV/cloudinit/control-node/user-data)
- [cloudinit/control-node/meta-data](C:/Users/Ziggi/AV/cloudinit/control-node/meta-data)

## Why the earlier attempts failed

1. The cloud image was initially treated like a raw disk, but it was actually `qcow2`.
2. Seed VHDX attachment on Hyper-V led to locking and differencing-disk issues.
3. The first ISO creation method exposed short filenames, which cloud-init ignored.
4. The first cloud-init password/user schema did not match the working configuration that finally produced a usable local account.
