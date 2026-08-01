#!/usr/bin/env bash
set -euo pipefail

BASE="${1:-/tmp/av-test-media}"
RAW="$BASE/raw"
MNT="/mnt/av-test-media"

sudo rm -rf "$RAW"
sudo mkdir -p "$RAW" "$MNT"

make_pdf() {
  local path="$1"
  local text="$2"
  sudo tee "$path" >/dev/null <<PDF
%PDF-1.1
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 64 >>
stream
BT /F1 16 Tf 36 96 Td ($text) Tj ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f
0000000010 00000 n
0000000063 00000 n
0000000122 00000 n
0000000248 00000 n
0000000362 00000 n
trailer
<< /Root 1 0 R /Size 6 >>
startxref
432
%%EOF
PDF
}

make_image() {
  local fs="$1"
  local name="$2"
  local label="$3"
  local output_stem="${4:-${name}-${fs}}"
  local img="$RAW/${output_stem}.img"

  sudo rm -f "$img"
  sudo truncate -s 128M "$img"

  local loopdev
  loopdev="$(sudo losetup --find --show "$img")"
  sudo parted -s "$loopdev" mklabel msdos
  sudo parted -s "$loopdev" mkpart primary 1MiB 100%
  sudo partprobe "$loopdev"
  sleep 1

  local part="${loopdev}p1"
  case "$fs" in
    ntfs) sudo mkfs.ntfs -F -L "$label" "$part" >/dev/null ;;
    exfat) sudo mkfs.exfat -L "$label" "$part" >/dev/null ;;
    fat32) sudo mkfs.vfat -F 32 -n "$label" "$part" >/dev/null ;;
    hfsplus) sudo mkfs.hfsplus -v "$label" "$part" >/dev/null ;;
    *) echo "Unsupported filesystem: $fs" >&2; return 1 ;;
  esac

  sudo mount "$part" "$MNT"
  sudo find "$MNT" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true

  case "$name" in
    infected-source)
      printf 'X5O!P%%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' | sudo tee "$MNT/EICAR.COM" >/dev/null
      sudo tee "$MNT/README.txt" >/dev/null <<TXT
This disk intentionally contains the EICAR test file.
Use it to verify that ClamAV blocks the media and produces a report.
TXT
      sudo mkdir -p "$MNT/samples"
      printf 'Synthetic malware trigger test set.\n' | sudo tee "$MNT/samples/notes.txt" >/dev/null
      ;;
    benign-source)
      make_pdf "$MNT/public-handout-01.pdf" "Public PDF sample 01"
      make_pdf "$MNT/public-handout-02.pdf" "Public PDF sample 02"
      sudo tee "$MNT/readme.txt" >/dev/null <<TXT
Benign removable-media set for offline AV validation.
Contains simple PDF, TXT, and CSV files.
TXT
      sudo tee "$MNT/inventory.csv" >/dev/null <<CSV
filename,type
public-handout-01.pdf,pdf
public-handout-02.pdf,pdf
readme.txt,text
CSV
      ;;
    clean-destination|clean-destination-ntfs-for-*)
      sudo tee "$MNT/DESTINATION-README.txt" >/dev/null <<TXT
Writable destination media for approved copy-out testing.
The PXE client should only write here after all active engines approve the source.
TXT
      ;;
    *)
      echo "Unsupported media type: $name" >&2
      sudo umount "$MNT"
      sudo losetup -d "$loopdev"
      return 1
      ;;
  esac

  sync
  sudo umount "$MNT"
  sudo losetup -d "$loopdev"
}

fs_code() {
  case "$1" in
    ntfs) printf 'NTF\n' ;;
    exfat) printf 'EXF\n' ;;
    fat32) printf 'FAT\n' ;;
    hfsplus) printf 'HFS\n' ;;
    *) echo "Unsupported filesystem code request: $1" >&2; return 1 ;;
  esac
}

for fs in ntfs exfat fat32 hfsplus; do
  code="$(fs_code "$fs")"
  make_image "$fs" infected-source "AVB-$code"
  make_image "$fs" benign-source "AVG-$code"
  make_image ntfs "clean-destination-ntfs-for-$fs" "AVD-$code" "clean-destination-ntfs-for-$fs"
done

sudo find "$RAW" -maxdepth 1 -type f -name '*.img' -printf '%f\n' | sort
