import logging
import re
import time
from functools import lru_cache
from typing import Iterator, Sequence
from uuid import NAMESPACE_URL, uuid5

from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.http import models

from .config import get_settings
from .tenant_context import get_current_user_id

logger = logging.getLogger(__name__)

EMBEDDING_SIZE = 1536
ASSISTANT_ID_PAYLOAD_KEY = "metadata.assistant_id"
USER_ID_PAYLOAD_KEY = "metadata.user_id"
FILE_ID_PAYLOAD_KEY = "metadata.file_id"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
SHARED_USER_ID = "default"
TICKER_ALIASES = {
    "AAPL": ("aapl", "apple", "苹果"),
    "AMZN": ("amzn", "amazon", "亚马逊"),
    "NVDA": ("nvda", "nvidia", "英伟达"),
    "MSFT": ("msft", "microsoft", "微软"),
    "GOOGL": ("googl", "google", "alphabet", "谷歌"),
    "GOOG": ("goog", "google", "alphabet", "谷歌"),
    "META": ("meta", "facebook", "脸书"),
    "TSLA": ("tsla", "tesla", "特斯拉"),
}


def get_embedding_api_key() -> str | None:
    settings = get_settings()
    return settings.openai_embedding_api_key or settings.openai_official_api_key


def validate_vectorstore_settings() -> None:
    settings = get_settings()

    if not get_embedding_api_key():
        raise RuntimeError(
            "OPENAI_EMBEDDING_API_KEY or OPENAI_OFFICIAL_API_KEY is not set "
            "in backend/.env"
        )
    if not settings.qdrant_url:
        raise RuntimeError("QDRANT_URL is not set in backend/.env")
    if not settings.qdrant_api_key:
        raise RuntimeError("QDRANT_API_KEY is not set in backend/.env")
    if not settings.qdrant_cloud_inference:
        raise RuntimeError(
            "QDRANT_CLOUD_INFERENCE must be enabled for server-side BM25"
        )


@lru_cache(maxsize=1)
def get_embeddings() -> OpenAIEmbeddings:
    validate_vectorstore_settings()
    settings = get_settings()
    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=get_embedding_api_key(),
        base_url=settings.openai_embedding_base_url or DEFAULT_OPENAI_BASE_URL,
    )


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    validate_vectorstore_settings()
    settings = get_settings()
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        cloud_inference=settings.qdrant_cloud_inference,
    )


def _collection_name(collection_name: str | None = None) -> str:
    return collection_name or get_settings().qdrant_collection


def _validate_collection_schema(collection_info: object) -> None:
    settings = get_settings()
    params = collection_info.config.params
    dense_vectors = params.vectors
    sparse_vectors = params.sparse_vectors or {}

    if not isinstance(dense_vectors, dict):
        raise RuntimeError(
            "Qdrant collection uses an unnamed dense vector; create a new "
            "hybrid collection instead of reusing the legacy collection"
        )

    dense_config = dense_vectors.get(settings.qdrant_dense_vector_name)
    if dense_config is None:
        raise RuntimeError(
            f"Qdrant collection is missing dense vector "
            f"'{settings.qdrant_dense_vector_name}'"
        )
    if dense_config.size != EMBEDDING_SIZE:
        raise RuntimeError(
            f"Qdrant dense vector size is {dense_config.size}; "
            f"expected {EMBEDDING_SIZE}"
        )
    if dense_config.distance != models.Distance.COSINE:
        raise RuntimeError("Qdrant dense vector must use cosine distance")

    sparse_config = sparse_vectors.get(settings.qdrant_bm25_vector_name)
    if sparse_config is None:
        raise RuntimeError(
            f"Qdrant collection is missing sparse vector "
            f"'{settings.qdrant_bm25_vector_name}'"
        )
    if sparse_config.modifier != models.Modifier.IDF:
        raise RuntimeError("Qdrant BM25 sparse vector must use the IDF modifier")


def ensure_collection_exists(collection_name: str | None = None) -> None:
    settings = get_settings()
    client = get_qdrant_client()
    target = _collection_name(collection_name)

    if not client.collection_exists(target):
        client.create_collection(
            collection_name=target,
            vectors_config={
                settings.qdrant_dense_vector_name: models.VectorParams(
                    size=EMBEDDING_SIZE,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                settings.qdrant_bm25_vector_name: models.SparseVectorParams(
                    modifier=models.Modifier.IDF,
                )
            },
        )

    collection_info = client.get_collection(target)
    _validate_collection_schema(collection_info)
    payload_schema = collection_info.payload_schema or {}
    required_indexes = {
        USER_ID_PAYLOAD_KEY: models.PayloadSchemaType.KEYWORD,
        ASSISTANT_ID_PAYLOAD_KEY: models.PayloadSchemaType.KEYWORD,
        FILE_ID_PAYLOAD_KEY: models.PayloadSchemaType.INTEGER,
    }
    for field_name, field_schema in required_indexes.items():
        if field_name not in payload_schema:
            client.create_payload_index(
                collection_name=target,
                field_name=field_name,
                field_schema=field_schema,
                wait=True,
            )


def make_chunk_point_id(chunk: dict) -> str:
    metadata = chunk["metadata"]
    raw_id = metadata.get("chunk_id") or (
        f"file-{metadata['file_id']}-chunk-{metadata['chunk_index']}"
    )
    return str(uuid5(NAMESPACE_URL, raw_id))


def make_bm25_document(text: str) -> models.Document:
    settings = get_settings()
    return models.Document(
        text=text,
        model=settings.qdrant_bm25_model,
        options={
            "language": settings.qdrant_bm25_language,
            "tokenizer": settings.qdrant_bm25_tokenizer,
        },
    )


def _query_entity_terms(query: str) -> set[str]:
    lowered = query.lower()
    terms: set[str] = set()
    explicit_tickers = {
        match.upper()
        for match in re.findall(r"(?<![A-Za-z])([A-Z]{2,5})(?![A-Za-z])", query)
    }
    for ticker, aliases in TICKER_ALIASES.items():
        if ticker in explicit_tickers or any(alias in lowered for alias in aliases):
            terms.update(aliases)
            terms.add(ticker.lower())
    for ticker in explicit_tickers:
        terms.add(ticker.lower())
    return terms


def _matches_entity_terms(item: dict, terms: set[str]) -> bool:
    metadata = item.get("metadata") or {}
    haystack = " ".join(
        [
            str(item.get("content") or ""),
            *(str(value) for value in metadata.values()),
        ]
    ).lower()
    return any(term in haystack for term in terms)


def _batches(items: Sequence[dict], size: int) -> Iterator[Sequence[dict]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def add_chunks_to_vectorstore(
    chunks: list[dict],
    collection_name: str | None = None,
) -> None:
    if not chunks:
        return

    settings = get_settings()
    target = _collection_name(collection_name)
    ensure_collection_exists(target)
    client = get_qdrant_client()
    embeddings = get_embeddings()

    for chunk_batch in _batches(chunks, settings.qdrant_upsert_batch_size):
        texts = [chunk["content"] for chunk in chunk_batch]
        dense_vectors = embeddings.embed_documents(texts)
        if len(dense_vectors) != len(chunk_batch):
            raise RuntimeError(
                "Dense embedding response count does not match chunk count"
            )

        points = []
        for chunk, dense_vector in zip(chunk_batch, dense_vectors, strict=True):
            points.append(
                models.PointStruct(
                    id=make_chunk_point_id(chunk),
                    vector={
                        settings.qdrant_dense_vector_name: dense_vector,
                        settings.qdrant_bm25_vector_name: make_bm25_document(
                            chunk["content"]
                        ),
                    },
                    payload={
                        "content": chunk["content"],
                        "metadata": chunk["metadata"],
                    },
                )
            )
        client.upsert(collection_name=target, points=points, wait=True)


def _file_filter(file_id: int) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key=FILE_ID_PAYLOAD_KEY,
                match=models.MatchValue(value=file_id),
            ),
        ]
    )


def _visible_user_filter(user_id: str | None = None) -> models.Filter:
    current_user_id = user_id or get_current_user_id() or SHARED_USER_ID
    visible_user_ids = {SHARED_USER_ID, current_user_id}
    conditions: list[models.Condition] = [
        models.FieldCondition(
            key=USER_ID_PAYLOAD_KEY,
            match=models.MatchValue(value=visible_user_id),
        )
        for visible_user_id in sorted(visible_user_ids)
    ]
    conditions.append(
        models.IsEmptyCondition(
            is_empty=models.PayloadField(key=USER_ID_PAYLOAD_KEY),
        )
    )
    return models.Filter(should=conditions)


def delete_file_chunks(
    user_id: str,
    file_id: int,
    collection_name: str | None = None,
) -> None:
    get_qdrant_client().delete(
        collection_name=_collection_name(collection_name),
        points_selector=models.FilterSelector(
            filter=_file_filter(file_id)
        ),
        wait=True,
    )


def count_file_chunks(
    user_id: str,
    file_id: int,
    collection_name: str | None = None,
) -> int:
    result = get_qdrant_client().count(
        collection_name=_collection_name(collection_name),
        count_filter=_file_filter(file_id),
        exact=True,
    )
    return result.count


def similarity_search(
    query: str,
    k: int = 4,
    user_id: str | None = None,
) -> list[dict]:
    settings = get_settings()
    target = _collection_name()
    ensure_collection_exists(target)
    started_at = time.perf_counter()
    visibility_filter = _visible_user_filter(user_id)

    try:
        dense_query = get_embeddings().embed_query(query)
        response = get_qdrant_client().query_points(
            collection_name=target,
            prefetch=[
                models.Prefetch(
                    query=dense_query,
                    using=settings.qdrant_dense_vector_name,
                    filter=visibility_filter,
                    limit=max(k, settings.rag_dense_candidate_count),
                ),
                models.Prefetch(
                    query=make_bm25_document(query),
                    using=settings.qdrant_bm25_vector_name,
                    filter=visibility_filter,
                    limit=max(k, settings.rag_bm25_candidate_count),
                ),
            ],
            query=models.RrfQuery(rrf=models.Rrf()),
            limit=k,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as exc:
        logger.exception(
            "Hybrid retrieval failed error_type=%s",
            exc.__class__.__name__,
        )
        raise

    results = []
    for point in response.points:
        payload = dict(point.payload or {})
        results.append(
            {
                "content": str(payload.get("content") or ""),
                "metadata": dict(payload.get("metadata") or {}),
                "score": point.score,
            }
        )
    entity_terms = _query_entity_terms(query)
    if entity_terms:
        results = [item for item in results if _matches_entity_terms(item, entity_terms)]
    logger.info(
        "Hybrid retrieval completed result_count=%s duration_ms=%.1f",
        len(results),
        (time.perf_counter() - started_at) * 1000,
    )
    return results
