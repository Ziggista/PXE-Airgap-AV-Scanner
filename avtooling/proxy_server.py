from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from avtooling.config import ensure_directory, load_json_file
from avtooling.logging_utils import configure_logging


class ProxyService:
    def __init__(self, config: dict[str, Any]) -> None:
        self.host = config.get("host", "127.0.0.1")
        self.port = int(config.get("port", 8080))
        self.timeout_seconds = int(config.get("timeout_seconds", 120))
        self.allowed_hosts = set(config.get("allowed_hosts", []))
        self.cache_dir = ensure_directory(config.get("cache_dir", "./runtime/proxy-cache"))
        self.logger = configure_logging("proxy-server", config.get("log_file"))

    def is_allowed(self, url: str) -> bool:
        parsed = urllib.parse.urlparse(url)
        return bool(parsed.hostname) and (
            not self.allowed_hosts or parsed.hostname.lower() in self.allowed_hosts
        )

    def fetch_to_cache(self, url: str) -> dict[str, Any]:
        if not self.is_allowed(url):
            raise PermissionError(f"Upstream host is not allowed: {url}")

        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        target = self.cache_dir / digest

        if target.exists():
            self.logger.info("Cache hit for %s", url)
            return {"cached": True, "path": str(target), "url": url}

        self.logger.info("Fetching %s", url)
        request = urllib.request.Request(url, headers={"User-Agent": "av-pxe-tooling/0.1"})
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = response.read()

        target.write_bytes(payload)
        return {"cached": False, "path": str(target), "url": url, "size": len(payload)}


def build_handler(service: ProxyService) -> type[BaseHTTPRequestHandler]:
    class ProxyHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/health":
                self._send_json({"status": "ok", "service": "proxy-server"})
                return

            if parsed.path != "/fetch":
                self._send_json({"error": "not-found"}, HTTPStatus.NOT_FOUND)
                return

            params = urllib.parse.parse_qs(parsed.query)
            target_url = params.get("url", [None])[0]
            if not target_url:
                self._send_json({"error": "missing-url"}, HTTPStatus.BAD_REQUEST)
                return

            try:
                result = service.fetch_to_cache(target_url)
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
            except urllib.error.URLError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            except Exception as exc:  # pragma: no cover
                service.logger.exception("Unhandled proxy error")
                self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
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

    return ProxyHandler


def run_server(config: dict[str, Any]) -> None:
    service = ProxyService(config)
    server = ThreadingHTTPServer((service.host, service.port), build_handler(service))
    service.logger.info("Proxy server listening on http://%s:%s", service.host, service.port)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the proxy-style fetch/cache server.")
    parser.add_argument("--config", required=True, help="Path to the JSON config file.")
    args = parser.parse_args()
    run_server(load_json_file(args.config))


if __name__ == "__main__":
    main()
