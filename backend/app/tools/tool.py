from langchain_core.tools import tool

from ..vectorstore import similarity_search


def format_search_results(results: list[dict]) -> str:
    if not results:
        return "No relevant chunks found."

    parts = []
    for index, item in enumerate(results, start=1):
        metadata = item["metadata"]
        parts.append(
            f"[{index}] "
            f"filename={metadata.get('filename')}, "
            f"file_id={metadata.get('file_id')}, "
            f"chunk_index={metadata.get('chunk_index')}\n"
            f"{item['content']}"
        )

    return "\n\n".join(parts)


@tool
def rag_search(query: str) -> str:
    """Search uploaded financial documents and return relevant chunks with source metadata."""
    results = similarity_search(
        query=query,
        assistant_id="default",
        k=4,
    )
    return format_search_results(results)
