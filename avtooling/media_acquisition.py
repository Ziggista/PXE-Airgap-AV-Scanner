from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from avtooling.config import ensure_directory, load_json_file
from avtooling.logging_utils import configure_logging


class MediaAcquisitionWorkflow:
    def __init__(self, config: dict[str, Any]) -> None:
        self.download_dir = ensure_directory(config.get("download_dir", "./runtime/downloads"))
        self.publish_dir = ensure_directory(config.get("publish_dir", "./runtime/published"))
        self.manifest_path = Path(
            config.get("manifest_path", "./runtime/manifests/acquired-media.json")
        ).resolve()
        self.logger = configure_logging("media-acquisition", config.get("log_file"))
        self.items = config.get("items", [])

    def run(self) -> Path:
        manifest_entries: list[dict[str, Any]] = []
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

        for item in self.items:
            if item.get("type", "download") == "download":
                manifest_entries.append(self._download_item(item))
            elif item["type"] == "copy":
                manifest_entries.append(self._copy_item(item))
            else:
                raise ValueError(f"Unsupported acquisition item type: {item['type']}")

        manifest = {
            "generated_utc": datetime.now(UTC).isoformat(),
            "items": manifest_entries,
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.logger.info("Acquisition manifest written to %s", self.manifest_path)
        return self.manifest_path

    def _download_item(self, item: dict[str, Any]) -> dict[str, Any]:
        url = item["url"]
        filename = item.get("filename") or Path(urllib.parse.urlparse(url).path).name
        target = self.download_dir / filename
        published = self.publish_dir / filename

        self.logger.info("Downloading %s", url)
        request = urllib.request.Request(url, headers={"User-Agent": "av-pxe-tooling/0.1"})
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = response.read()

        target.write_bytes(payload)
        shutil.copy2(target, published)

        return {
            "name": item.get("name", filename),
            "type": "download",
            "url": url,
            "downloaded_to": str(target),
            "published_to": str(published),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }

    def _copy_item(self, item: dict[str, Any]) -> dict[str, Any]:
        source = Path(item["source"]).resolve()
        if not source.exists():
            raise FileNotFoundError(f"Source item does not exist: {source}")

        target_name = item.get("filename", source.name)
        published = self.publish_dir / target_name
        shutil.copy2(source, published)
        payload = published.read_bytes()

        self.logger.info("Copied %s to %s", source, published)
        return {
            "name": item.get("name", target_name),
            "type": "copy",
            "source": str(source),
            "published_to": str(published),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }


def run_workflow(config: dict[str, Any]) -> Path:
    workflow = MediaAcquisitionWorkflow(config)
    return workflow.run()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Acquire boot/scanner media on Windows for later deployment into Ubuntu VMs."
    )
    parser.add_argument("--config", required=True, help="Path to the JSON config file.")
    args = parser.parse_args()
    run_workflow(load_json_file(args.config))


if __name__ == "__main__":
    main()
