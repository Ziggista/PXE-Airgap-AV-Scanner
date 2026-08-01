#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import wave
import zipfile
from pathlib import Path


EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
CHUNK_SIZE = 1024 * 1024


def minimal_docx_document_xml(extra_text: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r>
        <w:t>Airgap AV large document carrier fixture.</w:t>
      </w:r>
    </w:p>
    <w:p>
      <w:r>
        <w:t>{extra_text}</w:t>
      </w:r>
    </w:p>
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>
    </w:sectPr>
  </w:body>
</w:document>
"""


def create_large_docx(path: Path, target_size_mb: int = 160) -> None:
    target_size = target_size_mb * 1024 * 1024
    header = (
        b"Synthetic DOCX extension carrier for ClamAV large-file testing.\n"
        + EICAR
        + b"\nThis file is intentionally not a production document.\n"
    )
    with path.open("wb") as handle:
        handle.write(header)
        remaining = target_size - len(header)
        while remaining > 0:
            chunk = os.urandom(min(CHUNK_SIZE, remaining))
            handle.write(chunk)
            remaining -= len(chunk)


def create_large_wav(path: Path, target_size_mb: int = 160) -> None:
    target_audio_bytes = target_size_mb * 1024 * 1024
    sample_rate = 44100
    channels = 2
    sample_width = 2
    eicar_chunk = EICAR + b"\x00" * max(0, CHUNK_SIZE - len(EICAR))
    silence = b"\x00" * CHUNK_SIZE

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        written = 0
        first_chunk = eicar_chunk[: min(len(eicar_chunk), target_audio_bytes)]
        wav_file.writeframes(first_chunk)
        written += len(first_chunk)
        while written < target_audio_bytes:
            chunk = silence[: min(len(silence), target_audio_bytes - written)]
            wav_file.writeframes(chunk)
            written += len(chunk)


def create_macro_docm(path: Path) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="bin" ContentType="application/vnd.ms-office.vbaProject"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.ms-word.document.macroEnabled.main+xml"/>
</Types>
"""
    package_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""
    macro_blob = b"""
Sub AutoOpen()
  Dim s
  s = "powershell -nop -w hidden"
  CreateObject("WScript.Shell").Run s
End Sub

Private Sub Document_Open()
  Call AutoOpen
End Sub
"""
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", package_rels)
        archive.writestr("word/document.xml", minimal_docx_document_xml("Synthetic macro detection fixture."))
        archive.writestr("word/vbaProject.bin", macro_blob)


def create_javascript_pdf(path: Path) -> None:
    pdf = """%PDF-1.5
1 0 obj
<< /Type /Catalog /Pages 2 0 R /OpenAction 4 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R >>
endobj
4 0 obj
<< /S /JavaScript /JS (app.alert("airgap test"); this.exportDataObject({ cName:"sample.bin", nLaunch:2 });) >>
endobj
5 0 obj
<< /Length 66 >>
stream
BT
/F1 18 Tf
72 720 Td
(Synthetic PDF JavaScript detection fixture.) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f
0000000010 00000 n
0000000080 00000 n
0000000139 00000 n
0000000233 00000 n
0000000360 00000 n
trailer
<< /Root 1 0 R /Size 6 >>
startxref
479
%%EOF
"""
    path.write_text(pdf, encoding="ascii")


def create_javascript_fixture(path: Path) -> None:
    script = """var shell = new ActiveXObject("WScript.Shell");
var xhr = new ActiveXObject("MSXML2.XMLHTTP");
var cmd = "powershell -nop -w hidden";
shell.Run(cmd, 0, false);
eval(String.fromCharCode(99, 111, 100, 101));
"""
    path.write_text(script, encoding="ascii")


def create_manifest(path: Path) -> None:
    entries = []
    for item in sorted(path.iterdir()):
        if item.is_file():
            entries.append({"name": item.name, "size_bytes": item.stat().st_size})
    (path / "detection-corpus.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")


def populate_infected(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "README.txt").write_text(
        "\n".join(
            [
                "Synthetic malware-trigger test media.",
                "Contains EICAR carriers for ClamAV and suspicious fixtures for YARA.",
            ]
        ),
        encoding="ascii",
    )
    (output_dir / "EICAR.COM").write_bytes(EICAR)
    create_large_docx(output_dir / "large-eicar-carrier.docx")
    create_large_wav(output_dir / "large-eicar-carrier.wav")
    create_macro_docm(output_dir / "macro-suspicious-sample.docm")
    create_javascript_pdf(output_dir / "pdf-javascript-sample.pdf")
    create_javascript_fixture(output_dir / "downloader-suspicious-sample.js")
    create_manifest(output_dir)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--profile", choices=["infected-source"], default="infected-source")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if args.profile == "infected-source":
        populate_infected(output_dir)


if __name__ == "__main__":
    main()
