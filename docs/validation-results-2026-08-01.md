# PXE Client Validation Results - August 1, 2026

This note records the removable-media validation completed against the PXE client in the lab on Saturday, August 1, 2026.

## Scope completed

- active offline engines: `ClamAV` and `YARA`
- source filesystems exercised: `NTFS`, `exFAT`, `FAT32`, `HFS+`
- writable destination filesystem exercised: `NTFS`
- blocked path exercised with `EICAR.COM` test content
- approved path exercised with benign PDFs, TXT, and CSV content
- destination report bundle copy-out exercised for approved runs

## Artifact locations

Artifacts collected locally from the PXE client:

- [NTFS artifacts](C:\Users\Ziggi\AV\runtime\test-artifacts\ntfs)
- [exFAT artifacts](C:\Users\Ziggi\AV\runtime\test-artifacts\exfat)
- [FAT32 artifacts](C:\Users\Ziggi\AV\runtime\test-artifacts\fat32)
- [HFS+ artifacts](C:\Users\Ziggi\AV\runtime\test-artifacts\hfsplus)

Each source filesystem has:

- `infected/index.html`
- `infected/summary.json`
- `benign/index.html`
- `benign/summary.json`
- `benign/report-bundle/`

## What is proven

- `NTFS`, `exFAT`, `FAT32`, and `HFS+` source media were all mounted and scanned successfully.
- `NTFS` destination media accepted approved copy-out successfully.
- `ClamAV` blocked the infected source set in each exercised filesystem.
- `ClamAV` and `YARA` both returned clean on the benign source set in each exercised filesystem.
- The destination report bundle was written to the approved `NTFS` media for benign runs.
- The live report path captured the paired media labels correctly:
  - `AVG-NTF` -> `AVD-NTF`
  - `AVG-EXF` -> `AVD-EXF`
  - `AVG-FAT` -> `AVD-FAT`
  - `AVG-HFS` -> `AVD-HFS`
- The live report path normalized operator-facing filesystem names correctly:
  - source filesystems reported as `ntfs`, `exfat`, `fat32`, and `hfsplus`
  - destination filesystem reported as `ntfs` for every approved copy-out run

## Current release-state note

The published PXE image was rebuilt on Saturday, August 1, 2026 to normalize operator-facing filesystem names in the report path:

- `fuseblk` -> `NTFS`
- `vfat` -> `FAT32`

That rebuild completed successfully, published new PXE assets, and was validated with a fresh end-to-end media run across all four source filesystems with paired `NTFS` destinations.

## Fresh artifact set

The fresh paired-label validation artifacts are stored locally under:

- [runtime/test-artifacts/2026-08-01-paired](C:\Users\Ziggi\AV\runtime\test-artifacts\2026-08-01-paired)
