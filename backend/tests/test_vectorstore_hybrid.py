import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from qdrant_client.http import models

from app import vectorstore


def make_settings() -> SimpleNamespace:
    return SimpleNamespace(
        qdrant_collection="hybrid-test",
        qdrant_dense_vector_name="dense",
        qdrant_bm25_vector_name="bm25",
        qdrant_bm25_model="Qdrant/bm25",
        qdrant_bm25_language="none",
        qdrant_bm25_tokenizer="multilingual",
        qdrant_upsert_batch_size=2,
        rag_dense_candidate_count=20,
        rag_bm25_candidate_count=20,
    )


def collection_info() -> SimpleNamespace:
    params = SimpleNamespace(
        vectors={
            "dense": models.VectorParams(
                size=vectorstore.EMBEDDING_SIZE,
                distance=models.Distance.COSINE,
            )
        },
        sparse_vectors={
            "bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)
        },
    )
    return SimpleNamespace(
        config=SimpleNamespace(params=params),
        payload_schema={},
    )


class HybridCollectionTests(unittest.TestCase):
    def test_creates_named_dense_and_bm25_vectors(self):
        settings = make_settings()
        client = MagicMock()
        client.collection_exists.return_value = False
        client.get_collection.return_value = collection_info()

        with (
            patch.object(vectorstore, "get_settings", return_value=settings),
            patch.object(vectorstore, "get_qdrant_client", return_value=client),
        ):
            vectorstore.ensure_collection_exists()

        create_kwargs = client.create_collection.call_args.kwargs
        dense = create_kwargs["vectors_config"]["dense"]
        sparse = create_kwargs["sparse_vectors_config"]["bm25"]
        self.assertEqual(dense.size, vectorstore.EMBEDDING_SIZE)
        self.assertEqual(dense.distance, models.Distance.COSINE)
        self.assertEqual(sparse.modifier, models.Modifier.IDF)
        indexed_fields = {
            call.kwargs["field_name"]
            for call in client.create_payload_index.call_args_list
        }
        self.assertEqual(client.create_payload_index.call_count, 3)
        self.assertIn(vectorstore.USER_ID_PAYLOAD_KEY, indexed_fields)

    def test_rejects_legacy_unnamed_dense_collection(self):
        settings = make_settings()
        info = collection_info()
        info.config.params.vectors = models.VectorParams(
            size=vectorstore.EMBEDDING_SIZE,
            distance=models.Distance.COSINE,
        )

        with patch.object(vectorstore, "get_settings", return_value=settings):
            with self.assertRaisesRegex(RuntimeError, "unnamed dense vector"):
                vectorstore._validate_collection_schema(info)


class HybridIndexingTests(unittest.TestCase):
    def test_upserts_dense_and_server_side_bm25_in_batches(self):
        settings = make_settings()
        client = MagicMock()
        embeddings = MagicMock()
        embeddings.embed_documents.side_effect = [
            [[0.1] * vectorstore.EMBEDDING_SIZE] * 2,
            [[0.2] * vectorstore.EMBEDDING_SIZE],
        ]
        chunks = [
            {
                "content": f"AAPL financial chunk {index}",
                "metadata": {
                    "assistant_id": "default",
                    "user_id": "user-1",
                    "file_id": 10,
                    "chunk_index": index,
                },
            }
            for index in range(3)
        ]

        with (
            patch.object(vectorstore, "get_settings", return_value=settings),
            patch.object(vectorstore, "ensure_collection_exists"),
            patch.object(vectorstore, "get_qdrant_client", return_value=client),
            patch.object(vectorstore, "get_embeddings", return_value=embeddings),
        ):
            vectorstore.add_chunks_to_vectorstore(chunks)

        self.assertEqual(client.upsert.call_count, 2)
        first_points = client.upsert.call_args_list[0].kwargs["points"]
        self.assertEqual(len(first_points), 2)
        point = first_points[0]
        self.assertIn("dense", point.vector)
        bm25 = point.vector["bm25"]
        self.assertEqual(bm25.model, "Qdrant/bm25")
        self.assertEqual(
            bm25.options,
            {"language": "none", "tokenizer": "multilingual"},
        )
        self.assertEqual(point.payload["metadata"]["file_id"], 10)


class HybridSearchTests(unittest.TestCase):
    def test_queries_dense_and_bm25_then_fuses_with_rrf(self):
        settings = make_settings()
        embeddings = MagicMock()
        embeddings.embed_query.return_value = [0.3] * vectorstore.EMBEDDING_SIZE
        client = MagicMock()
        client.query_points.return_value = SimpleNamespace(
            points=[
                SimpleNamespace(
                    payload={
                        "content": "Net sales were 94.9 billion.",
                        "metadata": {
                            "assistant_id": "default",
                            "user_id": "user-1",
                            "filename": "AAPL_FY2025_Q1_financials.pdf",
                            "file_id": 10,
                            "chunk_index": 2,
                        },
                    },
                    score=0.75,
                )
            ]
        )

        with (
            patch.object(vectorstore, "get_settings", return_value=settings),
            patch.object(vectorstore, "ensure_collection_exists"),
            patch.object(vectorstore, "get_embeddings", return_value=embeddings),
            patch.object(vectorstore, "get_qdrant_client", return_value=client),
        ):
            results = vectorstore.similarity_search(
                "AAPL 2025 net sales",
                k=4,
            )

        query_kwargs = client.query_points.call_args.kwargs
        self.assertIsInstance(query_kwargs["query"], models.RrfQuery)
        self.assertEqual(len(query_kwargs["prefetch"]), 2)
        dense_prefetch, bm25_prefetch = query_kwargs["prefetch"]
        self.assertEqual(dense_prefetch.using, "dense")
        self.assertEqual(bm25_prefetch.using, "bm25")
        self.assertIsInstance(bm25_prefetch.query, models.Document)
        for prefetch in query_kwargs["prefetch"]:
            self.assertIsNone(prefetch.filter)
            self.assertEqual(prefetch.limit, 20)
        self.assertEqual(results[0]["score"], 0.75)
        self.assertEqual(results[0]["metadata"]["file_id"], 10)

    def test_filters_mismatched_ticker_results(self):
        settings = make_settings()
        embeddings = MagicMock()
        embeddings.embed_query.return_value = [0.3] * vectorstore.EMBEDDING_SIZE
        client = MagicMock()
        client.query_points.return_value = SimpleNamespace(
            points=[
                SimpleNamespace(
                    payload={
                        "content": "Apple net sales were higher.",
                        "metadata": {
                            "filename": "AAPL_FY2023_Q4_financial_statements.pdf",
                            "file_id": 170,
                        },
                    },
                    score=0.9,
                ),
                SimpleNamespace(
                    payload={
                        "content": "NVIDIA revenue increased.",
                        "metadata": {
                            "filename": "NVDA_FY2025_Q4_quarterly_presentation.pdf",
                            "file_id": 222,
                        },
                    },
                    score=0.8,
                ),
            ]
        )

        with (
            patch.object(vectorstore, "get_settings", return_value=settings),
            patch.object(vectorstore, "ensure_collection_exists"),
            patch.object(vectorstore, "get_embeddings", return_value=embeddings),
            patch.object(vectorstore, "get_qdrant_client", return_value=client),
        ):
            results = vectorstore.similarity_search("NVDA 最近几次财报怎么样", k=4)

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]["metadata"]["filename"],
            "NVDA_FY2025_Q4_quarterly_presentation.pdf",
        )


if __name__ == "__main__":
    unittest.main()
