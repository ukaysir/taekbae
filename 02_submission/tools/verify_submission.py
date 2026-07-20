from __future__ import annotations

import argparse
import json
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PdfReader


REQUIRED_TEXT = {
    "proposal": [
        "지정3",
        "대전 트램",
        "데이터 활용",
        "AI 활용",
        "분석방법",
        "타당성 및 차별성",
        "발전가능성",
        "78,607",
        "근거 보기",
        "공사정보 5건",
        "451개 기록",
    ],
    "report": [
        "데이터 수집",
        "활용 AI 도구",
        "주요 프롬프트",
        "AI 결과물 검토",
        "팀 기여",
        "공개 API",
        "78,607",
        "공사정보 5건",
        "근거 보기",
    ],
}

REQUIRED_IMAGE_COUNT = {
    "proposal": 3,
    "report": 2,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--type", choices=["proposal", "report"], required=True)
    parser.add_argument("--render-dir", type=Path, required=True)
    args = parser.parse_args()

    pdf_path = args.input.resolve()
    render_dir = args.render_dir.resolve()
    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    image_count = sum(len(page.images) for page in reader.pages)
    expected_range = (1, 10) if args.type == "proposal" else (3, 5)
    errors: list[str] = []
    if not expected_range[0] <= page_count <= expected_range[1]:
        errors.append(f"page_count {page_count} outside {expected_range}")
    if image_count < REQUIRED_IMAGE_COUNT[args.type]:
        errors.append(
            f"image_count {image_count} below required {REQUIRED_IMAGE_COUNT[args.type]}"
        )

    page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    for index, text in enumerate(page_texts, start=1):
        if len(text) < 80:
            errors.append(f"page {index} has too little extractable text: {len(text)}")
    all_text = "\n".join(page_texts)
    for required in REQUIRED_TEXT[args.type]:
        if required not in all_text:
            errors.append(f"missing required text: {required}")
    forbidden_text = {
        "local Windows path": "C:\\Users\\",
        "browser file URL": "file:///",
        "credential assignment": "DATA_GO_KR_SERVICE_KEY=",
    }
    for label, value in forbidden_text.items():
        if value in all_text:
            errors.append(f"forbidden text present: {label}")

    render_dir.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(str(pdf_path))
    rendered = []
    try:
        for index in range(len(document)):
            page = document[index]
            width, height = page.get_size()
            ratio = width / height if height else 0
            if abs(ratio - (210 / 297)) > 0.01:
                errors.append(f"page {index + 1} is not A4 portrait: {width}x{height}")
            bitmap = page.render(scale=1.5, rotation=0)
            image = bitmap.to_pil()
            target = render_dir / f"page-{index + 1:03d}.png"
            image.save(target)
            extrema = image.convert("L").getextrema()
            if extrema == (255, 255):
                errors.append(f"page {index + 1} rendered blank")
            rendered.append(str(target))
    finally:
        document.close()

    report = {
        "status": "valid" if not errors else "invalid",
        "input": str(pdf_path),
        "document_type": args.type,
        "pages": page_count,
        "images": image_count,
        "expected_page_range": list(expected_range),
        "errors": errors,
        "rendered_pages": rendered,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
