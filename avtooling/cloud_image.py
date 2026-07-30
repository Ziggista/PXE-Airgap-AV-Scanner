from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from avtooling.config import ensure_directory, load_json_file
from avtooling.logging_utils import configure_logging

VHD_FOOTER_COOKIE = b"conectix"
VHD_FEATURES = 0x00000002
VHD_FILE_FORMAT_VERSION = 0x00010000
VHD_DATA_OFFSET_FIXED = 0xFFFFFFFFFFFFFFFF
VHD_DISK_TYPE_FIXED = 2
SECONDS_FROM_1970_TO_2000 = 946684800
QCOW2_MAGIC = b"QFI\xfb"


def calculate_vhd_geometry(size_bytes: int) -> tuple[int, int, int]:
    total_sectors = size_bytes // 512
    if total_sectors > 65535 * 16 * 255:
        total_sectors = 65535 * 16 * 255

    if total_sectors >= 65535 * 16 * 63:
        sectors_per_track = 255
        heads = 16
        cylinders = total_sectors // (heads * sectors_per_track)
    else:
        sectors_per_track = 17
        cylinders_times_heads = total_sectors // sectors_per_track
        heads = max(4, math.ceil(cylinders_times_heads / 1024))

        if cylinders_times_heads >= heads * 1024 or heads > 16:
            sectors_per_track = 31
            heads = 16
            cylinders_times_heads = total_sectors // sectors_per_track

        if cylinders_times_heads >= heads * 1024:
            sectors_per_track = 63
            heads = 16
            cylinders_times_heads = total_sectors // sectors_per_track

        cylinders = cylinders_times_heads // heads

    return cylinders, heads, sectors_per_track


def build_fixed_vhd_footer(size_bytes: int) -> bytes:
    cylinders, heads, sectors_per_track = calculate_vhd_geometry(size_bytes)
    timestamp = int(datetime.now(UTC).timestamp()) - SECONDS_FROM_1970_TO_2000
    unique_id = uuid.uuid4().bytes

    footer = bytearray(512)
    struct.pack_into(">8s", footer, 0x00, VHD_FOOTER_COOKIE)
    struct.pack_into(">I", footer, 0x08, VHD_FEATURES)
    struct.pack_into(">I", footer, 0x0C, VHD_FILE_FORMAT_VERSION)
    struct.pack_into(">Q", footer, 0x10, VHD_DATA_OFFSET_FIXED)
    struct.pack_into(">I", footer, 0x18, timestamp)
    struct.pack_into(">4s", footer, 0x1C, b"pyvd")
    struct.pack_into(">I", footer, 0x20, 0x00010000)
    struct.pack_into(">4s", footer, 0x24, b"Wi2k")
    struct.pack_into(">Q", footer, 0x28, size_bytes)
    struct.pack_into(">Q", footer, 0x30, size_bytes)
    struct.pack_into(">H", footer, 0x38, cylinders)
    struct.pack_into(">B", footer, 0x3A, heads)
    struct.pack_into(">B", footer, 0x3B, sectors_per_track)
    struct.pack_into(">I", footer, 0x3C, VHD_DISK_TYPE_FIXED)
    struct.pack_into(">I", footer, 0x40, 0)
    struct.pack_into(">16s", footer, 0x44, unique_id)
    struct.pack_into(">B", footer, 0x54, 0)

    checksum = (~sum(footer) & 0xFFFFFFFF)
    struct.pack_into(">I", footer, 0x40, checksum)
    return bytes(footer)


class CloudImageWorkflow:
    def __init__(self, config: dict[str, Any]) -> None:
        self.download_dir = ensure_directory(config.get("download_dir", "./runtime/downloads"))
        self.output_dir = ensure_directory(config.get("output_dir", "./runtime/cloud-images"))
        self.manifest_path = Path(
            config.get("manifest_path", "./runtime/manifests/cloud-image-prep.json")
        ).resolve()
        self.logger = configure_logging("cloud-image", config.get("log_file"))
        self.image_url = config["image_url"]
        self.sha256sums_url = config["sha256sums_url"]
        self.image_filename = config["image_filename"]
        self.output_vhd_filename = config["output_vhd_filename"]

    def run(self) -> Path:
        raw_path = self._download(self.image_url, self.image_filename)
        sums_path = self._download(self.sha256sums_url, Path(self.sha256sums_url).name)
        actual_hash = self._sha256(raw_path)
        expected_hash = self._extract_expected_hash(sums_path, self.image_filename)
        if actual_hash.lower() != expected_hash.lower():
            raise ValueError(
                f"SHA256 mismatch for {self.image_filename}: {actual_hash} != {expected_hash}"
            )

        vhd_path = self.output_dir / self.output_vhd_filename
        self._convert_raw_to_fixed_vhd(raw_path, vhd_path)

        manifest = {
            "generated_utc": datetime.now(UTC).isoformat(),
            "image_url": self.image_url,
            "sha256sums_url": self.sha256sums_url,
            "raw_image_path": str(raw_path),
            "raw_image_sha256": actual_hash,
            "fixed_vhd_path": str(vhd_path),
        }
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.logger.info("Cloud image manifest written to %s", self.manifest_path)
        return self.manifest_path

    def _download(self, url: str, filename: str) -> Path:
        target = self.download_dir / filename
        if target.exists():
            self.logger.info("Using existing download %s", target)
            return target

        self.logger.info("Downloading %s", url)
        request = Request(url, headers={"User-Agent": "av-pxe-tooling/0.1"})
        with urlopen(request, timeout=600) as response:
            payload = response.read()
        target.write_bytes(payload)
        return target

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _extract_expected_hash(self, sums_path: Path, image_filename: str) -> str:
        for line in sums_path.read_text(encoding="utf-8").splitlines():
            if image_filename in line:
                return line.split()[0]
        raise ValueError(f"Could not find {image_filename} in {sums_path}")

    def _convert_raw_to_fixed_vhd(self, source: Path, destination: Path) -> None:
        with source.open("rb") as handle:
            header = handle.read(4)
        if header == QCOW2_MAGIC:
            raise ValueError(
                f"{source.name} is qcow2, not a raw disk image. "
                "Use a real qcow2-to-VHDX conversion step such as qemu-img before Hyper-V provisioning."
            )

        self.logger.info("Converting %s to fixed VHD %s", source, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        footer = build_fixed_vhd_footer(source.stat().st_size)

        with source.open("rb") as src, destination.open("wb") as dst:
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                dst.write(chunk)
            dst.write(footer)


def run_workflow(config: dict[str, Any]) -> Path:
    workflow = CloudImageWorkflow(config)
    return workflow.run()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download and prepare an Ubuntu cloud image for Hyper-V."
    )
    parser.add_argument("--config", required=True, help="Path to the JSON config file.")
    args = parser.parse_args()
    run_workflow(load_json_file(args.config))


if __name__ == "__main__":
    main()
