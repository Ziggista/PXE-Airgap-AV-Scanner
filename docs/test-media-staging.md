# Test Media Staging

This lab uses attachable `VHDX` media sets for Hyper-V testing of the PXE client.

## Current staged sets

For each source filesystem, create:

- `infected-source`
  - contains the standard `EICAR.COM` test string so `ClamAV` should detect and block it
- `benign-source`
  - contains simple public-style content such as PDFs, TXT, and CSV files

The writable destination media for operator validation should remain `NTFS`.
Each source filesystem should have its own matching destination identity so reports and copy-out verification are easy to trace.

## Filesystems to cover

The current source-media test matrix is:

- `NTFS`
- `exFAT`
- `FAT32`
- `HFS+`

Per Apple's Disk Utility guidance current as of Friday, July 31, 2026, the default Mac filesystem is `APFS`, while `MS-DOS (FAT)` and `ExFAT` are the Windows-compatible formats offered for external interoperability. Windows native tooling on this workstation can stage `NTFS`, `exFAT`, and `FAT32`, but not a real `APFS` volume. `HFS+` can be staged from the Ubuntu build VM, while `APFS` should remain a separate experimental track until the Linux tooling is validated. Source: [Apple Disk Utility file system formats](https://support.apple.com/en-euro/guide/disk-utility/dsku19ed921c/mac), [Apple disk image guidance](https://support.apple.com/en-mide/guide/disk-utility/dskutl11888/mac).

## Local staging script

Use:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\stage_test_media.ps1 -Force
```

Default behavior:

- creates all `NTFS`, `exFAT`, and `FAT32` sets under `C:\Users\Ziggi\AV\runtime\test-media`
- hot-attaches the `NTFS` source set plus the paired `NTFS` destination set to `av-pxe-uefi-test-vm`

Useful variants:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\stage_test_media.ps1 -AttachFileSystem exFAT -Force
powershell -ExecutionPolicy Bypass -File .\tools\stage_test_media.ps1 -AttachFileSystem FAT32 -Force
powershell -ExecutionPolicy Bypass -File .\tools\stage_test_media.ps1 -SkipAttach -Force
```

## Expected operator use

1. Boot the PXE client.
2. Mount the `infected-source` disk and verify `ClamAV` blocks it.
3. Mount the `benign-source` disk and verify `ClamAV` plus `YARA` approve it.
4. Mount the `NTFS` `clean-destination` disk and verify approved copy-out works.
5. Repeat with source media `NTFS`, then `exFAT`, then `FAT32`, then `HFS+`.

## Naming convention

Source labels:

- infected source: `AVB-NTF`, `AVB-EXF`, `AVB-FAT`, `AVB-HFS`
- benign source: `AVG-NTF`, `AVG-EXF`, `AVG-FAT`, `AVG-HFS`

Destination labels:

- paired `NTFS` destination: `AVD-NTF`, `AVD-EXF`, `AVD-FAT`, `AVD-HFS`

Destination file names should remain explicit, for example:

- `clean-destination-ntfs-for-ntfs.vhdx`
- `clean-destination-ntfs-for-exfat.vhdx`
- `clean-destination-ntfs-for-fat32.vhdx`
- `clean-destination-ntfs-for-hfsplus.vhdx`

## Reporting expectations

The operator-facing report should show:

- the source filesystem as `NTFS`, `exFAT`, `FAT32`, or `HFS+`
- the writable destination filesystem as `NTFS`
- the source and destination labels used during the scan

Kernel-native mount strings such as `fuseblk` and `vfat` should be normalized in the PXE client report before release validation is signed off.
