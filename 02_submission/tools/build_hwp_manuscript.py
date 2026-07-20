from __future__ import annotations

import argparse
import html
import re
from importlib.resources import files
from pathlib import Path
import winreg

import pandas as pd
from pyhwpx import Hwp


REPO_ROOT = Path(__file__).resolve().parents[2]
FIGURE_IMAGE = re.compile(r'<img\s+src="([^"]+)"[^>]*>', re.IGNORECASE)
FIGURE_CAPTION = re.compile(r'<figcaption>(.*?)</figcaption>', re.IGNORECASE | re.DOTALL)
INLINE_TOKEN = re.compile(r'(\*\*.+?\*\*|`.+?`|\[[^\]]+\]\([^)]+\))')
TABLE_DIVIDER = re.compile(r'^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$')


def split_table_row(line: str) -> list[str]:
    return [plain_inline(cell.strip()) for cell in line.strip().strip("|").split("|")]


def plain_inline(value: str) -> str:
    value = re.sub(r'\*\*(.+?)\*\*', r'\1', value)
    value = re.sub(r'`(.+?)`', r'\1', value)
    value = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', value)
    return value


def strip_html_markup(value: str) -> str:
    value = re.sub(r'<strong>(.*?)</strong>', r'**\1**', value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r'<[^>]+>', '', value)
    return html.unescape(value).strip()


def set_font(
    hwp: Hwp,
    *,
    size: float,
    bold: bool = False,
    color: tuple[int, int, int] = (16, 24, 40),
    face: str = "맑은 고딕",
) -> None:
    hwp.set_font(
        FaceName=face,
        Height=size,
        Bold=bold,
        TextColor=hwp.rgb_color(*color),
        Spacing=-2,
    )


def add_inline(
    hwp: Hwp,
    value: str,
    *,
    size: float,
    color: tuple[int, int, int] = (16, 24, 40),
    default_bold: bool = False,
) -> None:
    cursor = 0
    for match in INLINE_TOKEN.finditer(value):
        if match.start() > cursor:
            set_font(hwp, size=size, bold=default_bold, color=color)
            hwp.insert_text(value[cursor:match.start()])
        token = match.group(0)
        if token.startswith("**"):
            set_font(hwp, size=size, bold=True, color=color)
            hwp.insert_text(token[2:-2])
        elif token.startswith("`"):
            set_font(hwp, size=max(size - 0.4, 7), color=color, face="Consolas")
            hwp.insert_text(token[1:-1])
        else:
            link_match = re.fullmatch(r'\[([^\]]+)\]\(([^)]+)\)', token)
            label, url = link_match.groups() if link_match else (token, "")
            set_font(hwp, size=size, color=(23, 92, 211))
            hwp.insert_text(f"{label} ({url})")
        cursor = match.end()
    if cursor < len(value):
        set_font(hwp, size=size, bold=default_bold, color=color)
        hwp.insert_text(value[cursor:])


def configure_page(hwp: Hwp) -> None:
    page = hwp.get_pagedef_as_dict(as_="eng")
    page.update(
        {
            "TopMargin": 15,
            "BottomMargin": 18,
            "LeftMargin": 15,
            "RightMargin": 15,
            "HeaderLen": 7,
            "FooterLen": 7,
        }
    )
    if not hwp.set_pagedef(page, apply="all"):
        raise RuntimeError("failed to configure A4 page margins")
    if not hwp.page_num_pos(
        global_start=1,
        position="BottomCenter",
        number_format="Digit",
        side_char=False,
    ):
        raise RuntimeError("failed to insert page numbers")


def ensure_file_path_checker_module() -> None:
    module_path = Path(str(files("pyhwpx").joinpath("FilePathCheckerModule.dll"))).resolve()
    if not module_path.is_file():
        raise FileNotFoundError(module_path)
    registry_path = r"Software\HNC\HwpAutomation\Modules"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, registry_path) as key:
        winreg.SetValueEx(
            key,
            "FilePathCheckerModule",
            0,
            winreg.REG_SZ,
            str(module_path),
        )


def add_paragraph(hwp: Hwp, value: str, font_size: float, line_spacing: int) -> None:
    hwp.set_para(
        AlignType="Justify",
        LineSpacing=line_spacing,
        PrevSpacing=0,
        NextSpacing=2.2,
        WidowOrphan=1,
    )
    add_inline(hwp, value, size=font_size)
    hwp.BreakPara()


def add_heading(hwp: Hwp, value: str, level: int) -> None:
    sizes = {1: 18, 2: 13, 3: 10.5}
    colors = {1: (16, 24, 40), 2: (24, 73, 169), 3: (52, 64, 84)}
    hwp.set_para(
        AlignType="Left",
        LineSpacing=125,
        PrevSpacing=5 if level > 1 else 0,
        NextSpacing=4,
        KeepWithNext=1,
    )
    add_inline(
        hwp,
        value,
        size=sizes[level],
        color=colors[level],
        default_bold=True,
    )
    hwp.BreakPara()


def add_note(hwp: Hwp, value: str) -> None:
    hwp.set_para(
        AlignType="Left",
        LineSpacing=125,
        PrevSpacing=2,
        NextSpacing=6,
        LeftMargin=5,
        RightMargin=5,
    )
    add_inline(hwp, value, size=8, color=(145, 32, 24))
    hwp.BreakPara()


def add_list_item(
    hwp: Hwp,
    prefix: str,
    value: str,
    font_size: float,
    line_spacing: int,
) -> None:
    hwp.set_para(
        AlignType="Justify",
        LineSpacing=line_spacing,
        PrevSpacing=0,
        NextSpacing=1.2,
        LeftMargin=10,
        Indentation=-5,
        WidowOrphan=1,
    )
    set_font(hwp, size=font_size, bold=True)
    hwp.insert_text(prefix)
    add_inline(hwp, value, size=font_size)
    hwp.BreakPara()


def add_table(hwp: Hwp, rows: list[list[str]], font_size: float) -> None:
    column_count = max(len(row) for row in rows)
    normalized = [row + [""] * (column_count - len(row)) for row in rows]
    frame = pd.DataFrame(normalized[1:], columns=normalized[0])
    set_font(hwp, size=max(font_size - 0.8, 7.2))
    hwp.set_para(AlignType="Left", LineSpacing=105, PrevSpacing=0, NextSpacing=0)
    hwp.table_from_data(
        frame,
        header=True,
        index=False,
        treat_as_char=True,
        cell_fill=(228, 231, 236),
        header_bold=True,
    )
    hwp.MoveDocEnd()
    hwp.BreakPara()


def add_figure(hwp: Hwp, source: Path, block: str) -> None:
    image_match = FIGURE_IMAGE.search(block)
    caption_match = FIGURE_CAPTION.search(block)
    if not image_match:
        raise ValueError("figure is missing an image")
    image_path = (source.parent / image_match.group(1)).resolve()
    try:
        image_path.relative_to(REPO_ROOT)
    except ValueError as error:
        raise ValueError(f"figure image is outside repository: {image_path}") from error
    if not image_path.is_file():
        raise FileNotFoundError(image_path)
    hwp.set_para(
        AlignType="Center",
        LineSpacing=100,
        PrevSpacing=4,
        NextSpacing=1,
        KeepWithNext=1,
    )
    hwp.insert_picture(
        str(image_path),
        treat_as_char=True,
        embedded=True,
        sizeoption=1,
        width=174,
        height=97.875,
    )
    hwp.BreakPara()
    if caption_match:
        caption = strip_html_markup(caption_match.group(1))
        hwp.set_para(
            AlignType="Left",
            LineSpacing=115,
            PrevSpacing=1,
            NextSpacing=5,
            KeepWithNext=1,
        )
        add_inline(hwp, caption, size=7.4, color=(102, 112, 133))
        hwp.BreakPara()


def build_document(source: Path, hwp_path: Path, pdf_path: Path, document_type: str) -> int:
    font_size = 8.8 if document_type == "proposal" else 8.1
    line_spacing = 140 if document_type == "proposal" else 130
    lines = source.read_text(encoding="utf-8").splitlines()
    h2_indices = [index for index, line in enumerate(lines) if line.startswith("## ")]
    first_h2 = h2_indices[0] if h2_indices else -1
    last_h2 = h2_indices[-1] if h2_indices else -1

    ensure_file_path_checker_module()
    hwp = Hwp(new=True, visible=False, register_module=True)
    try:
        configure_page(hwp)
        index = 0
        paragraph_buffer: list[str] = []

        def flush_paragraph() -> None:
            nonlocal paragraph_buffer
            if paragraph_buffer:
                add_paragraph(
                    hwp,
                    " ".join(part.strip() for part in paragraph_buffer),
                    font_size,
                    line_spacing,
                )
                paragraph_buffer = []

        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            if not stripped:
                flush_paragraph()
                index += 1
                continue

            if stripped.startswith("<figure>"):
                flush_paragraph()
                block_lines = [line]
                while index + 1 < len(lines) and "</figure>" not in block_lines[-1]:
                    index += 1
                    block_lines.append(lines[index])
                add_figure(hwp, source, "\n".join(block_lines))
                index += 1
                continue

            heading_match = re.match(r'^(#{1,3})\s+(.+)$', line)
            if heading_match:
                flush_paragraph()
                level = len(heading_match.group(1))
                if (
                    document_type == "proposal"
                    and level == 2
                    and index not in (first_h2, last_h2)
                ):
                    hwp.BreakPage()
                add_heading(hwp, heading_match.group(2), level)
                index += 1
                continue

            if stripped.startswith("> "):
                flush_paragraph()
                add_note(hwp, stripped[2:])
                index += 1
                continue

            if (
                stripped.startswith("|")
                and index + 1 < len(lines)
                and TABLE_DIVIDER.match(lines[index + 1].strip())
            ):
                flush_paragraph()
                rows = [split_table_row(line)]
                index += 2
                while index < len(lines) and lines[index].strip().startswith("|"):
                    rows.append(split_table_row(lines[index]))
                    index += 1
                add_table(hwp, rows, font_size)
                continue

            ordered = re.match(r'^\s*(\d+)\.\s+(.+)$', line)
            bullet = re.match(r'^\s*[-*]\s+(.+)$', line)
            if ordered or bullet:
                flush_paragraph()
                prefix = f"{ordered.group(1)}. " if ordered else "• "
                value = ordered.group(2) if ordered else bullet.group(1)
                add_list_item(hwp, prefix, value, font_size, line_spacing)
                index += 1
                continue

            paragraph_buffer.append(stripped)
            index += 1

        flush_paragraph()
        hwp.RecalcPageCount()
        page_count = int(hwp.PageCount)
        hwp_path.parent.mkdir(parents=True, exist_ok=True)
        if not hwp.save_as(str(hwp_path), "HWP"):
            raise RuntimeError(f"failed to save HWP: {hwp_path}")
        if not hwp.save_as(str(pdf_path), "PDF"):
            raise RuntimeError(f"failed to save PDF: {pdf_path}")
        return page_count
    finally:
        hwp.quit(save=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--hwp", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--type", choices=("proposal", "report"), required=True)
    args = parser.parse_args()

    source = args.input.resolve()
    hwp_path = args.hwp.resolve()
    pdf_path = args.pdf.resolve()
    for target in (hwp_path, pdf_path):
        try:
            target.relative_to(REPO_ROOT)
        except ValueError as error:
            raise ValueError(f"output must stay inside repository: {target}") from error
    page_count = build_document(source, hwp_path, pdf_path, args.type)
    print(
        f"generated type={args.type} pages={page_count} "
        f"hwp={hwp_path} pdf={pdf_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
