from __future__ import annotations

import argparse
import json
import shutil
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from avtooling.config import ensure_directory, load_json_file
from avtooling.logging_utils import configure_logging


class BuildService:
    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "127.0.0.1")
        self.port = int(config.get("port", 8090))
        self.proxy_base_url = config.get("proxy_base_url", "http://127.0.0.1:8080")
        self.manifest_file = Path(config.get("manifest_file", "./runtime/manifests/boot.json")).resolve()
        self.stage_dir = ensure_directory(config.get("stage_dir", "./runtime/staged"))
        self.logger = configure_logging("build-server", config.get("log_file"))

    def fetch_via_proxy(self, url: str) -> dict[str, Any]:
        encoded = urllib.parse.urlencode({"url": url})
        request_url = f"{self.proxy_base_url}/fetch?{encoded}"
        with urllib.request.urlopen(request_url, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))

        source_path = Path(payload["path"]).resolve()
        destination = self.stage_dir / source_path.name
        shutil.copy2(source_path, destination)
        return {
            "source_url": url,
            "cached_path": str(source_path),
            "staged_path": str(destination),
        }

    def load_manifest(self) -> dict[str, Any]:
        with self.manifest_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)


def build_handler(service: BuildService) -> type[BaseHTTPRequestHandler]:
    class BuildHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)

            if parsed.path == "/health":
                self._send_json({"status": "ok", "service": "build-server"})
                return

            if parsed.path == "/manifest":
                self._send_json(service.load_manifest())
                return

            if parsed.path != "/stage":
                self._send_json({"error": "not-found"}, HTTPStatus.NOT_FOUND)
                return

            params = urllib.parse.parse_qs(parsed.query)
            source_url = params.get("url", [None])[0]
            if not source_url:
                self._send_json({"error": "missing-url"}, HTTPStatus.BAD_REQUEST)
                return

            try:
                result = service.fetch_via_proxy(source_url)
            except Exception as exc:  # pragma: no cover
                service.logger.exception("Build server stage request failed")
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            else:
                self._send_json(result)

        def log_message(self, format: str, *args: Any) -> None:
            service.logger.info("%s - %s", self.address_string(), format % args)

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return BuildHandler


def run_server(config: dict[str, Any]) -> None:
    service = BuildService(config)
    service.manifest_file.parent.mkdir(parents=True, exist_ok=True)
    if not service.manifest_file.exists():
        service.manifest_file.write_text(
            json.dumps(
                {
                    "boot_image": "winpe.wim",
                    "boot_loader": "wimboot",
                    "notes": "Replace with real PXE manifest data.",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    server = ThreadingHTTPServer((service.host, service.port), build_handler(service))
    service.logger.info("Build server listening on http://%s:%s", service.host, service.port)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the PXE build/staging server.")
    parser.add_argument("--config", required=True, help="Path to the JSON config file.")
    args = parser.parse_args()
    run_server(load_json_file(args.config))


if __name__ == "__main__":
    main()
