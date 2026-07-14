from __future__ import annotations

import argparse
import io
import subprocess
import tempfile
from pathlib import Path

import markdown
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


REPO_ROOT = Path(__file__).resolve().parents[1]
EDGE_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)


CSS = r"""
@page {
  size: A4;
  margin: 15mm 15mm 18mm 15mm;
}
* { box-sizing: border-box; }
html { color: #101828; background: white; }
body {
  margin: 0;
  font-family: "Malgun Gothic", "Noto Sans KR", sans-serif;
  font-size: 9.2pt;
  line-height: 1.48;
  word-break: keep-all;
  overflow-wrap: anywhere;
}
body.report { font-size: 8.55pt; line-height: 1.40; }
body::before {
  content: "DRAFT · 검토용";
  position: fixed;
  z-index: -1;
  left: 22%;
  top: 43%;
  transform: rotate(-28deg);
  color: rgba(180, 35, 24, 0.07);
  font-size: 48pt;
  font-weight: 800;
  white-space: nowrap;
}
h1 {
  margin: 0 0 5mm;
  padding-bottom: 3mm;
  border-bottom: 2px solid #344054;
  color: #101828;
  font-size: 18pt;
  line-height: 1.25;
  letter-spacing: -0.04em;
}
h2 {
  margin: 5mm 0 2.5mm;
  padding: 2.2mm 3mm;
  border-left: 4px solid #175cd3;
  background: #eff4ff;
  color: #1849a9;
  font-size: 13pt;
  line-height: 1.3;
  break-after: avoid-page;
}
body.proposal h2:not(:first-of-type):not(:last-of-type) { break-before: page; }
body.proposal h2:last-of-type ~ ol {
  columns: 2;
  column-gap: 6mm;
  font-size: 8.2pt;
  line-height: 1.25;
}
body.proposal h2:last-of-type ~ ol li {
  margin: 0.5mm 0;
  break-inside: avoid;
}
body.report h2:nth-of-type(3), body.report h2:nth-of-type(5) { break-before: page; }
h3 {
  margin: 3.5mm 0 1.4mm;
  color: #344054;
  font-size: 10.5pt;
  break-after: avoid-page;
}
p { margin: 1.6mm 0; orphans: 3; widows: 3; }
ul, ol { margin: 1.4mm 0 2mm 5.5mm; padding-left: 3mm; }
li { margin: 0.8mm 0; }
blockquote {
  margin: 0 0 4mm;
  padding: 2.5mm 3mm;
  border: 1px solid #fecdca;
  border-left: 4px solid #d92d20;
  background: #fef3f2;
  color: #912018;
  font-size: 8.5pt;
}
table {
  width: 100%;
  margin: 2.5mm 0 4mm;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 8.3pt;
}
body.report table { font-size: 7.8pt; }
th, td {
  padding: 1.7mm 2mm;
  border: 0.5px solid #98a2b3;
  vertical-align: top;
}
th { background: #e4e7ec; color: #101828; font-weight: 700; }
tr { break-inside: avoid; }
code {
  padding: 0.2mm 0.8mm;
  border-radius: 2px;
  background: #f2f4f7;
  color: #344054;
  font-family: Consolas, monospace;
  font-size: 0.92em;
}
pre { padding: 3mm; background: #101828; color: white; white-space: pre-wrap; }
a { color: #175cd3; text-decoration: none; }
strong { color: #101828; }
"""


def edge_path() -> Path:
    for candidate in EDGE_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Microsoft Edge was not found")


def build_html(source: Path, document_type: str) -> str:
    source_text = source.read_text(encoding="utf-8")
    content = markdown.markdown(
        source_text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    title = "제안서 초안" if document_type == "proposal" else "분석 과정 보고서 초안"
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body class="{document_type}">{content}</body>
</html>
"""


def print_pdf(html: Path, target: Path, profile_dir: Path) -> None:
    command = [
        str(edge_path()),
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--run-all-compositor-stages-before-draw",
        "--no-pdf-header-footer",
        f"--user-data-dir={profile_dir}",
        f"--print-to-pdf={target}",
        html.as_uri(),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
    if completed.returncode != 0 or not target.exists():
        message = (completed.stderr or completed.stdout or "Edge PDF generation failed").strip()
        raise RuntimeError(message[-1000:])


def add_page_numbers(source: Path, output: Path) -> int:
    reader = PdfReader(str(source))
    writer = PdfWriter()
    total = len(reader.pages)
    for index, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        overlay_buffer = io.BytesIO()
        overlay = canvas.Canvas(overlay_buffer, pagesize=(width, height))
        overlay.setFillColorRGB(0.4, 0.4, 0.4)
        overlay.setFont("Helvetica", 8)
        overlay.drawCentredString(width / 2, 18, f"{index} / {total}")
        overlay.save()
        overlay_buffer.seek(0)
        page.merge_page(PdfReader(overlay_buffer).pages[0])
        writer.add_page(page)
    writer.add_metadata(
        {
            "/Title": "대전 트램 공사구간의 도심배송 위험 관측·예보 모듈",
            "/Author": "[participant input required]",
            "/Subject": "2026 logistics data and AI competition draft",
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("wb") as handle:
        writer.write(handle)
    temporary.replace(output)
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--type", choices=["proposal", "report"], required=True)
    args = parser.parse_args()

    source = args.input.resolve()
    output = args.output.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.suffix.lower() != ".pdf":
        raise ValueError("output must be a PDF")

    temp_root = REPO_ROOT / ".tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="submission-", dir=temp_root) as temp_name:
        temp = Path(temp_name)
        html = temp / "document.html"
        raw_pdf = temp / "document.pdf"
        profile = temp / "edge-profile"
        html.write_text(build_html(source, args.type), encoding="utf-8", newline="\n")
        print_pdf(html, raw_pdf, profile)
        pages = add_page_numbers(raw_pdf, output)
    print(f"generated={output} pages={pages} type={args.type}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
