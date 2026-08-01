# Commercial Vendor Bundle Staging

As of Friday, July 31, 2026, the PXE client can consume staged commercial engine bundles, but Codex did not download any proprietary vendor package from Microsoft, Sophos, or Bitdefender because those downloads require your licensed tenant or portal access.

## Control-node staging path

Place vendor files on the control node checkout under:

- `/opt/av-pxe-tooling/runtime/vendor-bundles/defender/`
- `/opt/av-pxe-tooling/runtime/vendor-bundles/sophos/`
- `/opt/av-pxe-tooling/runtime/vendor-bundles/bitdefender/`

Those folders are copied into the PXE image at build time under:

- `/opt/av/bundles/defender/`
- `/opt/av/bundles/sophos/`
- `/opt/av/bundles/bitdefender/`

## Required manifest

Each staged bundle directory must contain `bundle-manifest.json`.

Supported schema:

```json
{
  "display_name": "Microsoft Defender for Endpoint",
  "scan_command": ["mdatp", "scan", "custom", "--path", "{source_path}"],
  "clean_exit_codes": [0],
  "detected_exit_codes": [1],
  "detection_markers": ["Threat", "Malware", "FOUND"]
}
```

`{source_path}` is replaced with the mounted public-media path during `offline-scan.sh`.

## Official command notes

- Microsoft Defender for Endpoint on Linux:
  - Official scanning CLI uses `mdatp scan custom --path <path>`
- Sophos Protection for Linux:
  - Official scanning CLI is `avscanner`
- Bitdefender Endpoint Security Tools:
  - Use the vendor-provided local CLI from your licensed package and place the exact invocation in `scan_command`

## Current behavior

- If no manifest is present, the commercial engine is marked `awaiting_bundle` or skipped at scan time.
- If a manifest is present in the built image, the readiness metadata changes to `bundle_staged`.
- `offline-scan.sh` will then attempt to execute the staged `scan_command` and include the result in the HTML/JSON report.
