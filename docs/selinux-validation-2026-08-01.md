# SELinux Validation - 2026-08-01

This note captures the SELinux permissive validation performed against the PXE client on Saturday, August 1, 2026.

## Outcome

SELinux was brought up successfully in `permissive` mode on the PXE client, and the client completed an end-to-end approved scan plus brokered copy-out run.

SELinux should **not** be switched to `enforcing` yet.

## What worked

- PXE client booted with:
  - `security=selinux`
  - `selinux=1`
  - `enforcing=0`
- The earlier relabel boot loop was removed by moving labeling work out of runtime and stopping the live image from creating `/.autorelabel`.
- The client reached:
  - `boot-started`
  - `definition-sync-ready`
  - `splash-ready`
  - `splash-debug-hold`
- A full approved scan succeeded:
  - run id: `20260801T062306`
  - source label: `AVG-NTF`
  - destination label: `AVD-NTF`
  - engines: `ClamAV`, `YARA`
  - overall status: `approved`
- Approved copy-out succeeded through the root broker:
  - scanned files copied to destination media
  - report bundle copied to `AV_SCAN_REPORTS/20260801T062306`

## Evidence

- Local artifact copy:
  - [runtime/test-artifacts/selinux-2026-08-01/ntfs-approved](C:\Users\Ziggi\AV\runtime\test-artifacts\selinux-2026-08-01\ntfs-approved)
- Local serial boot capture:
  - [runtime/logs/pxe-serial-20260801.log](C:\Users\Ziggi\AV\runtime\logs\pxe-serial-20260801.log)
  - [runtime/logs/pxe-serial-20260801-postfix.log](C:\Users\Ziggi\AV\runtime\logs\pxe-serial-20260801-postfix.log)
- PXE debug collector timeline:
  - `boot-started` at `2026-08-01T06:13:26+00:00`
  - `definition-sync-ready` at `2026-08-01T06:13:28+00:00`
  - `splash-ready` at `2026-08-01T06:14:53+00:00`
  - `splash-debug-hold` at `2026-08-01T06:14:57+00:00`

## Blocking issues before enforcing

- Early-boot AVC denials are still present for core services and generators, including:
  - `systemd_generator_t`
  - `cloud-init-gene`
  - `sshd-socket-gen`
  - `consolesetup_t`
  - `mount_t`
  - `udev_t`
- Example denial classes seen in permissive mode:
  - `read`
  - `open`
  - `create`
  - `append`
  - `unlink`
  - `search`
  - `sys_rawio`
  - `use`
  - `getattr`

These are currently permissive-only. In enforcing mode they are likely to break boot-time plumbing before or during kiosk startup.

- The non-root scan path also exposed a runtime ownership bug:
  - `/run/av-scan`
  - `/var/log/av-pxe/scans`

The scanner user could not create its run directory until ownership was corrected in the live session. The repo template has been updated, but the rebuilt image should be revalidated after that fix is baked in cleanly.

## Recommended next step

Keep SELinux in `permissive` mode while:

1. rebaking the scanner runtime ownership fix into the next PXE image
2. capturing a fresh permissive run without any live hotfixes
3. generating a minimal local policy or redesigning the image to remove the offending boot-time services

Only after that should `enforcing=1` be trialed.
