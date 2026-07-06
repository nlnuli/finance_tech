from __future__ import annotations

import sys
from pathlib import Path

from langchain_core.documents import Document


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.parsing import SUPPORTED_EXTENSIONS, parse_file  # noqa: E402


def split_csv_paths(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def collect_source_files(source_paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw_path in source_paths:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path

        if not path.exists():
            raise FileNotFoundError(f"Evaluation source path not found: {path}")

        if path.is_file():
            candidates = [path]
        else:
            candidates = [
                item for item in path.rglob("*") if item.is_file()
            ]

        for candidate in candidates:
            if candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(candidate)

    return sorted(set(files))


def load_eval_documents_from_files(files: list[Path]) -> list[Document]:
    documents: list[Document] = []
    for file_path in files:
        text = parse_file(file_path)
        if not text.strip():
            continue

        documents.append(
            Document(
                page_content=text,
                metadata={
                    "source": str(file_path),
                    "filename": file_path.name,
                    "extension": file_path.suffix.lower(),
                },
            )
        )

    if not documents:
        raise ValueError(
            "No supported evaluation documents found. "
            f"Supported extensions: {sorted(SUPPORTED_EXTENSIONS)}"
        )

    return documents


def load_eval_documents(source_paths: list[str]) -> list[Document]:
    return load_eval_documents_from_files(collect_source_files(source_paths))
