from langchain_text_splitters import RecursiveCharacterTextSplitter


CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def split_text_into_chunks(
    text: str,
    filename: str,
    assistant_id: str,
    file_id: int,
) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    texts = splitter.split_text(text)
    chunks = []

    for index, chunk_text in enumerate(texts):
        chunks.append(
            {
                "content": chunk_text,
                "metadata": {
                    "filename": filename,
                    "assistant_id": assistant_id,
                    "file_id": file_id,
                    "chunk_index": index,
                },
            }
        )

    return chunks
