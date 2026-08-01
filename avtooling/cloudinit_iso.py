from __future__ import annotations

import argparse
from pathlib import Path

import pycdlib


def _iso_name(name: str) -> str:
    sanitized = "".join(ch for ch in name.upper() if ch.isalnum() or ch == "_")
    return f"/{sanitized[:8]};1"


def build_cloudinit_iso(source_dir: Path, output_iso: Path, volume_label: str = "cidata") -> Path:
    source_dir = source_dir.resolve()
    output_iso = output_iso.resolve()

    meta_data = source_dir / "meta-data"
    user_data = source_dir / "user-data"
    network_config = source_dir / "network-config"
    if not meta_data.exists() or not user_data.exists():
        raise FileNotFoundError(
            f"{source_dir} must contain both 'meta-data' and 'user-data' files."
        )

    output_iso.parent.mkdir(parents=True, exist_ok=True)
    if output_iso.exists():
        output_iso.unlink()

    iso = pycdlib.PyCdlib()
    iso.new(
        interchange_level=3,
        joliet=3,
        rock_ridge="1.09",
        vol_ident=volume_label.upper(),
    )

    iso.add_file(
        str(meta_data),
        iso_path=_iso_name(meta_data.name),
        rr_name="meta-data",
        joliet_path="/meta-data",
    )
    iso.add_file(
        str(user_data),
        iso_path=_iso_name(user_data.name),
        rr_name="user-data",
        joliet_path="/user-data",
    )
    if network_config.exists():
        iso.add_file(
            str(network_config),
            iso_path=_iso_name(network_config.name),
            rr_name="network-config",
            joliet_path="/network-config",
        )

    iso.write(str(output_iso))
    iso.close()
    return output_iso


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a cloud-init cidata ISO with exact meta-data and user-data filenames."
    )
    parser.add_argument("--source-dir", required=True, help="Directory containing meta-data and user-data.")
    parser.add_argument("--output-iso", required=True, help="Path to write the cidata ISO.")
    parser.add_argument(
        "--volume-label",
        default="cidata",
        help="ISO volume label. Defaults to cidata.",
    )
    args = parser.parse_args()
    build_cloudinit_iso(Path(args.source_dir), Path(args.output_iso), args.volume_label)


if __name__ == "__main__":
    main()
