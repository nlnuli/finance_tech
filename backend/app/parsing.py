import re
from pathlib import Path

from docx import Document
from fastapi import HTTPException
from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def is_mergeable_short_line(line: str) -> bool:
    return len(line) <= 30 and not line.endswith((".", ":", ";", "?", "!"))


def is_short_line(line: str) -> bool:
    return len(line) <= 30


def find_next_non_empty_line(lines: list[str], start_index: int) -> str:
    for index in range(start_index, len(lines)):
        stripped = lines[index].strip()
        if stripped:
            return stripped

    return ""


def fix_short_line_breaks(text: str) -> str:
    lines = text.splitlines()
    fixed_lines = []
    short_line_buffer = []

    for index, line in enumerate(lines):
        stripped = line.strip()

        if not stripped:
            next_line = find_next_non_empty_line(lines, index + 1)
            if short_line_buffer and is_short_line(next_line):
                continue

            if short_line_buffer:
                fixed_lines.append(" ".join(short_line_buffer))
                short_line_buffer = []
            fixed_lines.append("")
            continue

        if is_mergeable_short_line(stripped):
            short_line_buffer.append(stripped)
            continue

        if short_line_buffer:
            short_line_buffer.append(stripped)
            fixed_lines.append(" ".join(short_line_buffer))
            short_line_buffer = []
        else:
            fixed_lines.append(stripped)

    if short_line_buffer:
        fixed_lines.append(" ".join(short_line_buffer))

    return "\n".join(fixed_lines)


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = fix_short_line_breaks(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_text_file(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8", errors="ignore")


def parse_pdf_file(file_path: Path) -> str:
    reader = PdfReader(str(file_path))
    page_texts = []

    for page in reader.pages:
        page_texts.append(page.extract_text() or "")

    return "\n\n".join(page_texts)


def parse_docx_file(file_path: Path) -> str:
    document = Document(str(file_path))
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    return "\n".join(paragraphs)


def parse_file(file_path: Path) -> str:
    extension = file_path.suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    if extension in {".txt", ".md"}:
        text = parse_text_file(file_path)
    elif extension == ".pdf":
        text = parse_pdf_file(file_path)
    else:
        text = parse_docx_file(file_path)

    return clean_text(text)
