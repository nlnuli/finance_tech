from __future__ import annotations

import sys
from pathlib import Path

from .models import RetrievedContext


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.vectorstore import similarity_search  # noqa: E402


def make_context_id(metadata: dict) -> str:
    filename = metadata.get("filename") or "unknown"
    file_id = metadata.get("file_id") or "unknown"
    chunk_index = metadata.get("chunk_index") or "unknown"
    return f"{filename}:{file_id}:{chunk_index}"


def docs_to_contexts(docs: list[dict]) -> list[RetrievedContext]:
    contexts: list[RetrievedContext] = []
    for doc in docs:
        metadata = dict(doc.get("metadata") or {})
        contexts.append(
            RetrievedContext(
                id=make_context_id(metadata),
                content=str(doc.get("content") or ""),
                filename=metadata.get("filename"),
                file_id=metadata.get("file_id"),
                chunk_index=metadata.get("chunk_index"),
                metadata=metadata,
            )
        )
    return contexts


def run_retrieval(
    query: str,
    assistant_id: str,
    retrieval_k: int,
) -> list[RetrievedContext]:
    docs = similarity_search(
        query=query,
        assistant_id=assistant_id,
        k=retrieval_k,
    )
    return docs_to_contexts(docs)


def format_contexts(contexts: list[RetrievedContext]) -> str:
    if not contexts:
        return "No relevant chunks found."

    parts = []
    for index, context in enumerate(contexts, start=1):
        parts.append(
            f"[{index}] "
            f"filename={context.filename}, "
            f"file_id={context.file_id}, "
            f"chunk_index={context.chunk_index}\n"
            f"{context.content}"
        )
    return "\n\n".join(parts)
