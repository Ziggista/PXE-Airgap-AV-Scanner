from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from avtooling.config import ensure_directory, load_json_file
from avtooling.logging_utils import configure_logging


@dataclass
class EngineResult:
    name: str
    return_code: int
    command: str
    status: str
    output: str


class OfflineScanWorkflow:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.source_path = Path(config["source_path"]).resolve()
        self.destination_path = Path(config["destination_path"]).resolve()
        self.report_dir = ensure_directory(config.get("report_dir", "./runtime/reports"))
        self.logger = configure_logging("pxe-client", config.get("log_file"))
        self.allowed_exit_codes = set(config.get("allowed_exit_codes", [0]))

    def validate_paths(self) -> None:
        if not self.source_path.exists():
            raise FileNotFoundError(f"Source path does not exist: {self.source_path}")
        if not self.destination_path.exists():
            self.destination_path.mkdir(parents=True, exist_ok=True)

    def run_engines(self) -> list[EngineResult]:
        results: list[EngineResult] = []
        for engine in self.config.get("engines", []):
            if not engine.get("enabled", True):
                continue

            command = self._render_command(engine["command"])
            argv = split_command(command)
            self.logger.info("Running engine '%s': %s", engine["name"], command)
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                shell=False,
                check=False,
            )
            combined_output = (completed.stdout or "") + (completed.stderr or "")
            status = "passed" if completed.returncode in self.allowed_exit_codes else "failed"
            results.append(
                EngineResult(
                    name=engine["name"],
                    return_code=completed.returncode,
                    command=command,
                    status=status,
                    output=combined_output.strip(),
                )
            )

        return results

    def copy_if_clean(self, results: list[EngineResult]) -> bool:
        if any(result.status != "passed" for result in results):
            self.logger.warning("Copy blocked because one or more engines failed.")
            return False

        target = self.destination_path / self.source_path.name
        if self.source_path.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(self.source_path, target)
        else:
            shutil.copy2(self.source_path, target)

        self.logger.info("Copied clean media to %s", target)
        return True

    def write_report(self, results: list[EngineResult], copied: bool) -> Path:
        report = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "source_path": str(self.source_path),
            "destination_path": str(self.destination_path),
            "copied": copied,
            "results": [result.__dict__ for result in results],
        }
        report_path = self.report_dir / f"scan-report-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report_path

    def run(self) -> Path:
        self.validate_paths()
        results = self.run_engines()
        copied = self.copy_if_clean(results)
        report_path = self.write_report(results, copied)
        self.logger.info("Workflow complete. Report written to %s", report_path)
        return report_path

    def _render_command(self, template: str) -> str:
        rendered = template.format(
            source_path=str(self.source_path),
            destination_path=str(self.destination_path),
        )
        return rendered


def split_command(command: str) -> list[str]:
    return shlex.split(command, posix=False)


def run_workflow(config: dict[str, Any]) -> Path:
    workflow = OfflineScanWorkflow(config)
    return workflow.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline PXE client scan workflow.")
    parser.add_argument("--config", required=True, help="Path to the JSON config file.")
    args = parser.parse_args()
    run_workflow(load_json_file(args.config))


if __name__ == "__main__":
    main()
