import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.document_processing.models import TextBlock, UnifiedDocument
from scripts import reindex_qdrant_hybrid as reindex


class HybridReindexTests(unittest.TestCase):
    def test_loads_pdf_chunks_from_fused_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_dir = Path(temp_dir)
            document = UnifiedDocument(
                file_id=1,
                filename="old-name.pdf",
                page_count=1,
                blocks=[
                    TextBlock(
                        id="ocr-1",
                        page_number=1,
                        text="AAPL net sales",
                        source_processors=["ocr"],
                    )
                ],
            )
            (artifact_dir / "fused.json").write_text(
                document.model_dump_json(),
                encoding="utf-8",
            )
            record = {
                "id": 41,
                "user_id": "user-1",
                "assistant_id": "default",
                "original_name": "report.pdf",
                "file_path": str(artifact_dir / "missing-source.pdf"),
                "artifact_dir": str(artifact_dir),
                "status": "ready",
            }

            chunks, page_count = reindex.load_chunks_for_file(record)

            self.assertEqual(page_count, 1)
            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0]["metadata"]["file_id"], 41)
            self.assertEqual(chunks[0]["metadata"]["filename"], "report.pdf")
            self.assertFalse((artifact_dir / "table-stitching.json").exists())

    def test_recognizes_only_indexing_failures_with_fused_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_dir = Path(temp_dir)
            (artifact_dir / "fused.json").write_text("{}", encoding="utf-8")
            (artifact_dir / "manifest.json").write_text(
                json.dumps({"status": "failed", "failed_stage": "indexing"}),
                encoding="utf-8",
            )
            record = {
                "status": "failed",
                "artifact_dir": str(artifact_dir),
            }

            self.assertTrue(reindex.is_recoverable_index_failure(record))

            (artifact_dir / "manifest.json").write_text(
                json.dumps({"status": "failed", "failed_stage": "processing"}),
                encoding="utf-8",
            )
            self.assertFalse(reindex.is_recoverable_index_failure(record))

    def test_persisted_pdf_reindex_writes_stitching_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_dir = Path(temp_dir)
            document = UnifiedDocument(
                file_id=43,
                filename="report.pdf",
                page_count=1,
            )
            (artifact_dir / "fused.json").write_text(
                document.model_dump_json(),
                encoding="utf-8",
            )
            (artifact_dir / "manifest.json").write_text(
                json.dumps({"status": "ready", "summary": {"artifacts": {}}}),
                encoding="utf-8",
            )
            record = {
                "id": 43,
                "user_id": "user-1",
                "assistant_id": "default",
                "original_name": "report.pdf",
                "file_path": str(artifact_dir / "missing.pdf"),
                "artifact_dir": str(artifact_dir),
                "status": "ready",
            }

            chunks, page_count = reindex.load_chunks_for_file(
                record,
                persist_stitching=True,
            )

            self.assertEqual(chunks, [])
            self.assertEqual(page_count, 1)
            self.assertTrue((artifact_dir / "table-stitching.json").exists())
            manifest = json.loads(
                (artifact_dir / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["summary"]["artifacts"]["table_stitching"],
                "table-stitching.json",
            )

    def test_reindex_replaces_points_verifies_count_and_recovers_status(self):
        record = {
            "id": 41,
            "user_id": "user-1",
            "assistant_id": "default",
            "original_name": "report.pdf",
            "artifact_dir": "/tmp/artifacts/41",
            "status": "failed",
        }
        chunks = [
            {
                "content": "financial text",
                "metadata": {
                    "assistant_id": "default",
                    "user_id": "user-1",
                    "file_id": 41,
                    "chunk_index": 0,
                },
            }
        ]

        with (
            patch.object(
                reindex, "load_chunks_for_file", return_value=(chunks, 3)
            ) as load_chunks,
            patch.object(reindex, "delete_file_chunks") as delete_chunks,
            patch.object(reindex, "add_chunks_to_vectorstore") as add_chunks,
            patch.object(reindex, "count_file_chunks", return_value=1),
            patch.object(reindex, "mark_manifest_recovered") as mark_recovered,
            patch.object(reindex, "update_file_processing") as update_file,
        ):
            count = reindex.reindex_file(
                record,
                target_collection="hybrid-v1",
                retries=0,
                retry_delay=0,
            )

        self.assertEqual(count, 1)
        load_chunks.assert_called_once_with(record, persist_stitching=True)
        delete_chunks.assert_called_once_with("user-1", 41, "hybrid-v1")
        add_chunks.assert_called_once_with(chunks, "hybrid-v1")
        mark_recovered.assert_called_once_with(record)
        update_file.assert_called_once_with(
            41,
            "ready",
            page_count=3,
            chunk_count=1,
            artifact_dir="/tmp/artifacts/41",
            processing_error=None,
        )


if __name__ == "__main__":
    unittest.main()
