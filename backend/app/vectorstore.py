from functools import lru_cache
from uuid import NAMESPACE_URL, uuid5

from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http import models

from .config import get_settings


EMBEDDING_SIZE = 1536
ASSISTANT_ID_PAYLOAD_KEY = "metadata.assistant_id"


def validate_vectorstore_settings() -> None:
    settings = get_settings()

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in backend/.env")

    if not settings.qdrant_url:
        raise RuntimeError("QDRANT_URL is not set in backend/.env")

    if not settings.qdrant_api_key:
        raise RuntimeError("QDRANT_API_KEY is not set in backend/.env")


@lru_cache(maxsize=1)
def get_embeddings() -> OpenAIEmbeddings:
    validate_vectorstore_settings()
    settings = get_settings()

    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    validate_vectorstore_settings()
    settings = get_settings()

    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )


def ensure_collection_exists() -> None:
    settings = get_settings()
    client = get_qdrant_client()

    if not client.collection_exists(settings.qdrant_collection):
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=models.VectorParams(
                size=EMBEDDING_SIZE,
                distance=models.Distance.COSINE,
            ),
        )

    collection_info = client.get_collection(settings.qdrant_collection)
    if ASSISTANT_ID_PAYLOAD_KEY in collection_info.payload_schema:
        return

    client.create_payload_index(
        collection_name=settings.qdrant_collection,
        field_name=ASSISTANT_ID_PAYLOAD_KEY,
        field_schema=models.PayloadSchemaType.KEYWORD,
    )


@lru_cache(maxsize=1)
def get_vectorstore() -> QdrantVectorStore:
    ensure_collection_exists()
    settings = get_settings()

    return QdrantVectorStore(
        client=get_qdrant_client(),
        collection_name=settings.qdrant_collection,
        embedding=get_embeddings(),
    )


def make_chunk_point_id(chunk: dict) -> str:
    metadata = chunk["metadata"]
    raw_id = f"file-{metadata['file_id']}-chunk-{metadata['chunk_index']}"
    return str(uuid5(NAMESPACE_URL, raw_id))


def add_chunks_to_vectorstore(chunks: list[dict]) -> None:
    if not chunks:
        return

    vectorstore = get_vectorstore()
    texts = [chunk["content"] for chunk in chunks]
    metadatas = [chunk["metadata"] for chunk in chunks]
    ids = [make_chunk_point_id(chunk) for chunk in chunks]

    vectorstore.add_texts(
        texts=texts,
        metadatas=metadatas,
        ids=ids,
    )


def similarity_search(
    query: str,
    assistant_id: str = "default",
    k: int = 4,
) -> list[dict]:
    assistant_filter = models.Filter(
        must=[
            models.FieldCondition(
                key=ASSISTANT_ID_PAYLOAD_KEY,
                match=models.MatchValue(value=assistant_id),
            )
        ]
    )

    docs = get_vectorstore().similarity_search(
        query=query,
        k=k,
        filter=assistant_filter,
    )

    return [
        {
            "content": doc.page_content,
            "metadata": doc.metadata,
        }
        for doc in docs
    ]
