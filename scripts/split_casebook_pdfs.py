from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter

DEFAULT_INPUT_ROOT = Path(
    r"D:\Project\lawyer\Resource\law_documents\中国法院2025年度案例"
)
DEFAULT_START_PADDING = 12.0
FRONT_MATTER_TITLES = {"序", "目录", "目 录", "contents", "content"}
SECTION_TITLE_RE = re.compile(r"^[一二三四五六七八九十百零]+、")
SUBSECTION_TITLE_RE = re.compile(r"^[（(][^)）]+[)）]$")
INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
FOOTNOTE_MARK_RE = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]")
WHITESPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class OutlineLeaf:
    title: str
    page_index: int
    top: float | None
    parent_titles: tuple[str, ...]


@dataclass(slots=True)
class SplitRecord:
    case_index: int
    title: str
    parent_titles: tuple[str, ...]
    source_pdf: str
    output_pdf: str
    start_page: int
    end_page: int
    start_top: float | None
    next_start_page: int | None
    next_start_top: float | None
    output_pages: int
    cropped_start_page: bool
    cropped_end_page: bool


@dataclass(slots=True)
class SplitSummary:
    source_pdf: str
    output_dir: str
    case_count: int
    manifest_path: str | None


def normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = FOOTNOTE_MARK_RE.sub("", normalized)
    normalized = normalized.replace("\u3000", " ")
    return WHITESPACE_RE.sub(" ", normalized).strip()


def sanitize_filename(value: str, max_length: int = 96) -> str:
    safe = normalize_title(value)
    safe = INVALID_FILENAME_CHARS_RE.sub("_", safe)
    safe = safe.strip(" .")
    if not safe:
        safe = "untitled"
    return safe[:max_length].rstrip(" .")


def is_case_title(title: str) -> bool:
    normalized = normalize_title(title)
    if not normalized:
        return False
    if normalized.lower() in FRONT_MATTER_TITLES:
        return False
    if SECTION_TITLE_RE.match(normalized):
        return False
    if SUBSECTION_TITLE_RE.match(normalized):
        return False
    return True


def extract_outline_leaf_nodes(
    reader: PdfReader,
    outline_items: list[Any],
    parent_titles: tuple[str, ...] = (),
) -> list[OutlineLeaf]:
    leaves: list[OutlineLeaf] = []
    index = 0

    while index < len(outline_items):
        item = outline_items[index]
        if isinstance(item, list):
            leaves.extend(extract_outline_leaf_nodes(reader, item, parent_titles))
            index += 1
            continue

        title = normalize_title(
            str(getattr(item, "title", None) or item.get("/Title") or "")
        )
        has_children = index + 1 < len(outline_items) and isinstance(
            outline_items[index + 1], list
        )

        page_index = reader.get_destination_page_number(item)
        top_value = item.get("/Top")
        top = float(top_value) if top_value is not None else None

        if has_children:
            leaves.extend(
                extract_outline_leaf_nodes(
                    reader,
                    outline_items[index + 1],
                    (*parent_titles, title),
                )
            )
            index += 2
            continue

        leaves.append(
            OutlineLeaf(
                title=title,
                page_index=page_index,
                top=top,
                parent_titles=parent_titles,
            )
        )
        index += 1

    return leaves


def collect_case_bookmarks(reader: PdfReader) -> list[OutlineLeaf]:
    outline = getattr(reader, "outline", None)
    if not outline:
        return []

    leaves = extract_outline_leaf_nodes(reader, outline)
    return [leaf for leaf in leaves if is_case_title(leaf.title)]


def add_cropped_page(
    writer: PdfWriter,
    source_page,
    *,
    lower_y: float | None = None,
    upper_y: float | None = None,
) -> bool:
    page_bottom = float(source_page.mediabox.bottom)
    page_top = float(source_page.mediabox.top)
    page_left = float(source_page.mediabox.left)
    page_right = float(source_page.mediabox.right)

    crop_lower = max(page_bottom, lower_y if lower_y is not None else page_bottom)
    crop_upper = min(page_top, upper_y if upper_y is not None else page_top)

    if crop_upper <= crop_lower:
        return False

    cloned_page = source_page.clone(writer, force_duplicate=True)
    if crop_lower > page_bottom or crop_upper < page_top:
        for box_name in ("mediabox", "cropbox", "trimbox", "bleedbox", "artbox"):
            box = getattr(cloned_page, box_name, None)
            if box is None:
                continue
            box.lower_left = (page_left, crop_lower)
            box.upper_right = (page_right, crop_upper)

    writer.add_page(cloned_page)
    return True


def determine_output_root(input_path: Path) -> Path:
    if input_path.is_file():
        return input_path.with_name(f"{input_path.stem}_拆分案件")
    return input_path.parent / f"{input_path.name}_拆分案件"


def collect_pdf_paths(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    return sorted(path for path in input_path.rglob("*.pdf") if path.is_file())


def split_single_pdf(
    source_pdf: Path,
    output_dir: Path,
    *,
    start_padding: float = DEFAULT_START_PADDING,
) -> SplitSummary:
    reader = PdfReader(str(source_pdf))
    case_bookmarks = collect_case_bookmarks(reader)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not case_bookmarks:
        return SplitSummary(
            source_pdf=str(source_pdf),
            output_dir=str(output_dir),
            case_count=0,
            manifest_path=None,
        )

    records: list[SplitRecord] = []

    for case_index, bookmark in enumerate(case_bookmarks, start=1):
        next_bookmark = (
            case_bookmarks[case_index] if case_index < len(case_bookmarks) else None
        )
        last_page_index = (
            next_bookmark.page_index if next_bookmark else len(reader.pages) - 1
        )

        writer = PdfWriter()
        output_pages = 0

        for page_index in range(bookmark.page_index, last_page_index + 1):
            source_page = reader.pages[page_index]
            lower_y: float | None = None
            upper_y: float | None = None

            if page_index == bookmark.page_index and bookmark.top is not None:
                upper_y = bookmark.top + start_padding

            if (
                next_bookmark is not None
                and page_index == next_bookmark.page_index
                and next_bookmark.top is not None
            ):
                lower_y = next_bookmark.top

            if add_cropped_page(
                writer,
                source_page,
                lower_y=lower_y,
                upper_y=upper_y,
            ):
                output_pages += 1

        safe_title = sanitize_filename(bookmark.title)
        output_pdf = output_dir / f"{case_index:03d}_{safe_title}.pdf"
        with output_pdf.open("wb") as file:
            writer.write(file)

        records.append(
            SplitRecord(
                case_index=case_index,
                title=bookmark.title,
                parent_titles=bookmark.parent_titles,
                source_pdf=str(source_pdf),
                output_pdf=str(output_pdf),
                start_page=bookmark.page_index + 1,
                end_page=last_page_index + 1,
                start_top=bookmark.top,
                next_start_page=next_bookmark.page_index + 1
                if next_bookmark
                else None,
                next_start_top=next_bookmark.top if next_bookmark else None,
                output_pages=output_pages,
                cropped_start_page=bookmark.top is not None,
                cropped_end_page=next_bookmark is not None
                and next_bookmark.top is not None,
            )
        )

    manifest_path = output_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as file:
        json.dump(
            [asdict(record) for record in records],
            file,
            ensure_ascii=False,
            indent=2,
        )

    return SplitSummary(
        source_pdf=str(source_pdf),
        output_dir=str(output_dir),
        case_count=len(records),
        manifest_path=str(manifest_path),
    )


def split_pdf_tree(
    input_path: Path,
    output_root: Path,
    *,
    start_padding: float = DEFAULT_START_PADDING,
    limit: int | None = None,
) -> tuple[list[SplitSummary], list[str]]:
    pdf_paths = collect_pdf_paths(input_path)
    if limit is not None:
        pdf_paths = pdf_paths[:limit]

    summaries: list[SplitSummary] = []
    errors: list[str] = []

    for source_pdf in pdf_paths:
        try:
            if input_path.is_file():
                target_dir = output_root
            else:
                relative_parent = source_pdf.parent.relative_to(input_path)
                target_dir = output_root / relative_parent / sanitize_filename(
                    source_pdf.stem
                )
            summary = split_single_pdf(
                source_pdf,
                target_dir,
                start_padding=start_padding,
            )
            summaries.append(summary)
        except Exception as exc:  # pragma: no cover - CLI safety path
            errors.append(f"{source_pdf}: {exc}")

    return summaries, errors


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "按 PDF 书签把《中国法院2025年度案例》这类案例汇编拆成单独案件 PDF。"
        )
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        default=str(DEFAULT_INPUT_ROOT),
        help="待处理的目录或单个 PDF，默认是仓库里的《中国法院2025年度案例》目录。",
    )
    parser.add_argument(
        "--output-root",
        dest="output_root",
        default=None,
        help="输出目录。未指定时会在输入目录旁边创建“*_拆分案件”。",
    )
    parser.add_argument(
        "--start-padding",
        type=float,
        default=DEFAULT_START_PADDING,
        help="案件起始页向上额外保留的点数，默认 12。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="只处理前 N 个 PDF，便于先小范围试跑。",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    input_path = Path(args.input_path).expanduser().resolve()
    if not input_path.exists():
        parser.error(f"输入路径不存在: {input_path}")

    output_root = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else determine_output_root(input_path)
    )
    output_root.mkdir(parents=True, exist_ok=True)

    summaries, errors = split_pdf_tree(
        input_path,
        output_root,
        start_padding=args.start_padding,
        limit=args.limit,
    )

    split_case_total = sum(summary.case_count for summary in summaries)
    print(f"输入路径: {input_path}")
    print(f"输出目录: {output_root}")
    print(f"已处理 PDF: {len(summaries)}")
    print(f"已拆出案件 PDF: {split_case_total}")

    for summary in summaries:
        if summary.case_count == 0:
            print(f"[SKIP] {summary.source_pdf} 未发现可拆分案件书签")
            continue
        print(
            f"[OK] {summary.source_pdf} -> {summary.case_count} 个案件，输出到 {summary.output_dir}"
        )

    if errors:
        print("\n以下文件处理失败：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
