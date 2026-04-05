from dataclasses import dataclass
import re

from app.services.loaders.base import LoadedFragment


CLAUSE_HEADING_PATTERNS = (
    re.compile(r"^第[一二三四五六七八九十百千零\d]+条"),
    re.compile(r"^[一二三四五六七八九十]+[、.]"),
    re.compile(r"^\d+(?:\.\d+){1,3}\s*"),
    re.compile(r"^[（(]\d+[)）]"),
)


@dataclass(slots=True)
class ParsedClause:
    clause_path: str
    title: str
    clause_index: int
    page_start: int
    page_end: int
    content: str
    metadata: dict


def _is_heading(line: str) -> bool:
    text = line.strip()
    if not text:
        return False
    return any(pattern.match(text) for pattern in CLAUSE_HEADING_PATTERNS)


def _fallback_clauses(fragments: list[LoadedFragment]) -> list[ParsedClause]:
    clauses: list[ParsedClause] = []
    paragraph_index = 0
    for fragment in fragments:
        paragraphs = [
            part.strip()
            for part in re.split(r"\n{2,}", fragment.content)
            if part.strip()
        ]
        for paragraph in paragraphs:
            title = paragraph.splitlines()[0][:40] or f"段落 {paragraph_index + 1}"
            clauses.append(
                ParsedClause(
                    clause_path=f"P{paragraph_index + 1:03d}",
                    title=title,
                    clause_index=paragraph_index,
                    page_start=fragment.page_number,
                    page_end=fragment.page_number,
                    content=paragraph,
                    metadata={"source": "paragraph-fallback"},
                )
            )
            paragraph_index += 1

    if clauses:
        return clauses

    return [
        ParsedClause(
            clause_path="P001",
            title="全文摘要",
            clause_index=0,
            page_start=0,
            page_end=0,
            content="未能提取可审查条款内容。",
            metadata={"source": "empty-fallback"},
        )
    ]


def parse_clauses(fragments: list[LoadedFragment]) -> list[ParsedClause]:
    clauses: list[ParsedClause] = []
    current_title: str | None = None
    current_lines: list[str] = []
    current_page_start = 0
    current_page_end = 0
    clause_index = 0

    def flush() -> None:
        nonlocal current_title, current_lines, current_page_start, current_page_end, clause_index
        content = "\n".join(line for line in current_lines if line.strip()).strip()
        if not content:
            return
        title = current_title or (content.splitlines()[0][:40] or f"条款 {clause_index + 1}")
        clauses.append(
            ParsedClause(
                clause_path=f"C{clause_index + 1:03d}",
                title=title,
                clause_index=clause_index,
                page_start=current_page_start,
                page_end=current_page_end or current_page_start,
                content=content,
                metadata={"source": "heading" if current_title else "paragraph"},
            )
        )
        clause_index += 1
        current_title = None
        current_lines = []
        current_page_start = 0
        current_page_end = 0

    for fragment in fragments:
        lines = [line.strip() for line in fragment.content.splitlines() if line.strip()]
        if not lines:
            continue
        for line in lines:
            if _is_heading(line):
                flush()
                current_title = line[:120]
                current_lines = [line]
                current_page_start = fragment.page_number
                current_page_end = fragment.page_number
                continue

            if not current_lines:
                current_page_start = fragment.page_number
            current_lines.append(line)
            current_page_end = fragment.page_number

    flush()
    return clauses if clauses else _fallback_clauses(fragments)
