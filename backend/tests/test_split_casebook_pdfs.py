from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import Fit


def load_script_module():
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "split_casebook_pdfs.py"
    )
    spec = importlib.util.spec_from_file_location("split_casebook_pdfs", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def create_sample_casebook_pdf(pdf_path: Path) -> None:
    writer = PdfWriter()
    for _ in range(2):
        writer.add_blank_page(width=200, height=400)

    writer.add_outline_item("序", 0, fit=Fit.xyz(top=395))
    chapter = writer.add_outline_item("一、示例章节", 0, fit=Fit.xyz(top=380))
    section = writer.add_outline_item(
        "(一)示例分类", 0, parent=chapter, fit=Fit.xyz(top=360)
    )
    writer.add_outline_item("案例一标题", 0, parent=section, fit=Fit.xyz(top=300))
    writer.add_outline_item("案例二标题", 0, parent=section, fit=Fit.xyz(top=120))
    writer.add_outline_item("案例三标题", 1, parent=section, fit=Fit.xyz(top=250))

    with pdf_path.open("wb") as file:
        writer.write(file)


def test_collect_case_bookmarks_filters_outline_headings(tmp_path: Path) -> None:
    module = load_script_module()
    pdf_path = tmp_path / "sample.pdf"
    create_sample_casebook_pdf(pdf_path)

    reader = PdfReader(str(pdf_path))
    bookmarks = module.collect_case_bookmarks(reader)

    assert [item.title for item in bookmarks] == [
        "案例一标题",
        "案例二标题",
        "案例三标题",
    ]
    assert bookmarks[0].parent_titles == ("一、示例章节", "(一)示例分类")


def test_split_single_pdf_crops_boundary_pages(tmp_path: Path) -> None:
    module = load_script_module()
    pdf_path = tmp_path / "sample.pdf"
    output_dir = tmp_path / "out"
    create_sample_casebook_pdf(pdf_path)

    summary = module.split_single_pdf(pdf_path, output_dir, start_padding=0)

    assert summary.case_count == 3

    output_files = sorted(
        path for path in output_dir.glob("*.pdf") if path.name != "manifest.json"
    )
    assert [path.name for path in output_files] == [
        "001_案例一标题.pdf",
        "002_案例二标题.pdf",
        "003_案例三标题.pdf",
    ]

    first_case = PdfReader(str(output_files[0]))
    assert len(first_case.pages) == 1
    assert float(first_case.pages[0].mediabox.bottom) == 120.0
    assert float(first_case.pages[0].mediabox.top) == 300.0

    second_case = PdfReader(str(output_files[1]))
    assert len(second_case.pages) == 2
    assert float(second_case.pages[0].mediabox.bottom) == 0.0
    assert float(second_case.pages[0].mediabox.top) == 120.0
    assert float(second_case.pages[1].mediabox.bottom) == 250.0
    assert float(second_case.pages[1].mediabox.top) == 400.0

    third_case = PdfReader(str(output_files[2]))
    assert len(third_case.pages) == 1
    assert float(third_case.pages[0].mediabox.bottom) == 0.0
    assert float(third_case.pages[0].mediabox.top) == 250.0

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert [item["title"] for item in manifest] == [
        "案例一标题",
        "案例二标题",
        "案例三标题",
    ]
