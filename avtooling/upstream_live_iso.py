from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from avtooling.config import ensure_directory
from avtooling.logging_utils import configure_logging


def _run_powershell(command: str) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class UpstreamLiveIsoStager:
    def __init__(
        self,
        iso_path: str | Path,
        profile_name: str,
        publish_dir: str | Path = "./runtime/published",
        manifest_dir: str | Path = "./runtime/manifests",
        log_file: str | Path | None = None,
    ) -> None:
        self.iso_path = Path(iso_path).expanduser().resolve()
        self.profile_name = profile_name
        self.publish_dir = ensure_directory(publish_dir)
        self.manifest_dir = ensure_directory(manifest_dir)
        self.logger = configure_logging("upstream-live-iso", log_file)

    def run(self) -> Path:
        if not self.iso_path.exists():
            raise FileNotFoundError(f"ISO not found: {self.iso_path}")

        profile_dir = ensure_directory(self.publish_dir / self.profile_name)
        published_iso_path = self.publish_dir / self.iso_path.name
        published_kernel_path = profile_dir / "vmlinuz"
        published_initrd_path = profile_dir / "initrd"

        self.logger.info("Publishing ISO %s to %s", self.iso_path, published_iso_path)
        shutil.copy2(self.iso_path, published_iso_path)

        drive_letter = self._mount_iso()
        try:
            casper_root = Path(f"{drive_letter}:/casper")
            kernel_source = casper_root / "vmlinuz"
            initrd_source = casper_root / "initrd"

            if not kernel_source.exists() or not initrd_source.exists():
                raise FileNotFoundError(
                    f"Expected casper boot files were not found under {casper_root}"
                )

            shutil.copy2(kernel_source, published_kernel_path)
            shutil.copy2(initrd_source, published_initrd_path)
        finally:
            self._dismount_iso()

        manifest = {
            "generated_utc": datetime.now(UTC).isoformat(),
            "profile_name": self.profile_name,
            "iso_path": str(self.iso_path),
            "published_iso_path": str(published_iso_path.resolve()),
            "published_kernel_path": str(published_kernel_path.resolve()),
            "published_initrd_path": str(published_initrd_path.resolve()),
        }

        manifest_path = self.manifest_dir / f"{self.profile_name}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.logger.info("Wrote upstream live ISO manifest to %s", manifest_path)
        return manifest_path

    def _mount_iso(self) -> str:
        command = (
            "$mount = Mount-DiskImage -ImagePath "
            f"'{self.iso_path}' -PassThru; "
            "($mount | Get-Volume).DriveLetter"
        )
        drive_letter = _run_powershell(command)
        if not drive_letter:
            raise RuntimeError(f"Unable to resolve drive letter for mounted ISO {self.iso_path}")
        self.logger.info("Mounted %s as %s:", self.iso_path, drive_letter)
        return drive_letter

    def _dismount_iso(self) -> None:
        command = f"Dismount-DiskImage -ImagePath '{self.iso_path}'"
        _run_powershell(command)
        self.logger.info("Dismounted %s", self.iso_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage an upstream Ubuntu live ISO and extract its casper kernel/initrd."
    )
    parser.add_argument("--iso", required=True, help="Path to the downloaded Ubuntu live ISO.")
    parser.add_argument(
        "--profile-name",
        required=True,
        help="Published PXE profile name, for example ubuntu-live-desktop.",
    )
    parser.add_argument(
        "--publish-dir",
        default="./runtime/published",
        help="Directory used to publish the ISO and extracted boot files.",
    )
    parser.add_argument(
        "--manifest-dir",
        default="./runtime/manifests",
        help="Directory used to write the generated manifest JSON.",
    )
    parser.add_argument("--log-file", default=None, help="Optional log file path.")
    args = parser.parse_args()

    stager = UpstreamLiveIsoStager(
        iso_path=args.iso,
        profile_name=args.profile_name,
        publish_dir=args.publish_dir,
        manifest_dir=args.manifest_dir,
        log_file=args.log_file,
    )
    stager.run()


if __name__ == "__main__":
    main()
