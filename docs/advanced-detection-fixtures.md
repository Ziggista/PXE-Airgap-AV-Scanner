# Advanced Detection Fixtures

This project includes a synthetic offline-detection corpus for proving `ClamAV` and `YARA` behaviour against larger and more realistic-looking staged files.

## Fixture set

The generator is [tools/generate_detection_corpus.py](C:\Users\Ziggi\AV\tools\generate_detection_corpus.py).

It creates:

- `EICAR.COM`
- `large-eicar-carrier.docx`
  - synthetic `150 MB+` document-extension carrier for offline scanner stress testing
- `large-eicar-carrier.wav`
  - synthetic `150 MB+` audio carrier for offline scanner stress testing
- `macro-suspicious-sample.docm`
  - smaller macro-style fixture for `YARA`
- `pdf-javascript-sample.pdf`
  - smaller PDF JavaScript fixture for `YARA`
- `downloader-suspicious-sample.js`
  - smaller script fixture for `YARA`

## Current proven behaviour

As tested on Saturday, August 1, 2026:

- `ClamAV` reliably detects the standalone `EICAR.COM`.
- `ClamAV` scans through the `150 MB+` carrier files when `--max-filesize=0`, `--max-scansize=0`, and `--max-scantime=0` are applied, but it does not currently flag those carriers as infected.
- `YARA` reliably detects:
  - the macro-style `.docm`
  - the JavaScript-bearing `.pdf`
  - the suspicious downloader `.js`
  - the large synthetic `.docx` carrier
  - the large synthetic `.wav` carrier

## Operational meaning

This gives two layers of proof:

- `ClamAV` still demonstrates the signature path using `EICAR.COM`
- `YARA` demonstrates offline policy detection on larger carrier-style files and smaller suspicious-content fixtures

## Evidence

The current proof run is stored in:

- [runtime/test-artifacts/2026-08-01-advanced-detection](C:\Users\Ziggi\AV\runtime\test-artifacts\2026-08-01-advanced-detection)
