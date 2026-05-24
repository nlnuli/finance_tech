import re
from pathlib import Path

from docx import Document
from fastapi import HTTPException
from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", text)
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
