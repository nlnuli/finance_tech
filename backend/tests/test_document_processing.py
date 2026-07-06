import json
import tempfile
import unittest
from datetime import datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import UploadFile
from google.cloud import documentai_v1
from pypdf import PdfReader, PdfWriter

from app.document_processing.chunking import build_document_chunks
from app.document_processing.client import ProcessorCallResult, split_pdf_batches
from app.document_processing.fusion import fuse_documents
from app.document_processing.models import (
    BoundingBox,
    DocumentTable,
    NormalizedDocument,
    PageInfo,
    TableCell,
    TableRow,
    TextBlock,
)
from app.document_processing.normalize import normalize_document
from app.document_processing.service import (
    DocumentProcessingError,
    DocumentProcessingService,
    record_processing_failure,
)
from app.document_processing.models import UnifiedDocument
from app.document_processing.service import DocumentProcessingResult
from app.uploads import upload_file
from app.schemas import FileUploadResponse
from app.vectorstore import make_chunk_point_id


def make_pdf(page_count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def make_google_document(page_count: int) -> object:
    text_parts = []
    pages = []
    offset = 0
    for page_index in range(page_count):
        page_text = f"page {page_index + 1} financial text"
        text_parts.append(page_text)
        end = offset + len(page_text)
        pages.append(
            {
                "dimension": {"width": 100, "height": 100},
                "blocks": [
                    {
                        "layout": {
                            "text_anchor": {
                                "text_segments": [
                                    {"start_index": offset, "end_index": end}
                                ]
                            },
                            "bounding_poly": {
                                "normalized_vertices": [
                                    {"x": 0.1, "y": 0.1},
                                    {"x": 0.9, "y": 0.1},
                                    {"x": 0.9, "y": 0.2},
                                    {"x": 0.1, "y": 0.2},
                                ]
                            },
                            "confidence": 0.95,
                        }
                    }
                ],
            }
        )
        offset = end + 1
    return documentai_v1.Document(text="\n".join(text_parts), pages=pages)


class FakeDocumentAIClient:
    def __init__(self, form_processor_id: str, fail_form: bool = False):
        self.form_processor_id = form_processor_id
        self.fail_form = fail_form
        self.calls = []

    async def process(
        self, processor_id: str, content: bytes, mime_type="application/pdf"
    ):
        page_count = len(PdfReader(BytesIO(content)).pages)
        self.calls.append((processor_id, page_count))
        if self.fail_form and processor_id == self.form_processor_id:
            raise RuntimeError("form processor unavailable")
        return ProcessorCallResult(
            document=make_google_document(page_count),
            processor_id=processor_id,
            processor_name=f"processors/{processor_id}",
            attempts=1,
            duration_seconds=0.01,
        )


class DocumentNormalizationTests(unittest.TestCase):
    def test_normalizes_text_anchor_and_global_page_offset(self):
        normalized = normalize_document(
            make_google_document(1),
            processor_kind="ocr",
            processor_id="ocr-id",
            page_offset=15,
        )

        self.assertEqual(normalized.pages[0].page_number, 16)
        self.assertEqual(normalized.blocks[0].page_number, 16)
        self.assertEqual(normalized.blocks[0].text, "page 1 financial text")
        self.assertAlmostEqual(normalized.blocks[0].bounding_box.left, 0.1)

    def test_splits_pdf_into_expected_page_batches(self):
        batches = split_pdf_batches(make_pdf(20), page_batch_size=15)

        self.assertEqual(
            [(batch.start_page, batch.end_page) for batch in batches],
            [(1, 15), (16, 20)],
        )

    def test_recursively_splits_a_batch_that_exceeds_byte_limit(self):
        content = make_pdf(2)
        single_page_size = max(
            len(batch.content)
            for batch in split_pdf_batches(content, page_batch_size=1)
        )

        batches = split_pdf_batches(
            content,
            page_batch_size=2,
            max_batch_bytes=single_page_size,
        )

        self.assertEqual(len(batches), 2)
        self.assertEqual(
            [(batch.start_page, batch.end_page) for batch in batches], [(1, 1), (2, 2)]
        )

    def test_normalizes_form_table_and_key_value_field(self):
        text = "Revenue2025100"
        document = documentai_v1.Document(
            text=text,
            pages=[
                {
                    "dimension": {"width": 100, "height": 100},
                    "tables": [
                        {
                            "layout": {
                                "bounding_poly": {
                                    "normalized_vertices": [
                                        {"x": 0.1, "y": 0.3},
                                        {"x": 0.9, "y": 0.3},
                                        {"x": 0.9, "y": 0.8},
                                        {"x": 0.1, "y": 0.8},
                                    ]
                                }
                            },
                            "header_rows": [
                                {
                                    "cells": [
                                        {
                                            "layout": {
                                                "text_anchor": {
                                                    "text_segments": [
                                                        {
                                                            "start_index": 0,
                                                            "end_index": 7,
                                                        }
                                                    ]
                                                }
                                            }
                                        }
                                    ]
                                }
                            ],
                            "body_rows": [
                                {
                                    "cells": [
                                        {
                                            "layout": {
                                                "text_anchor": {
                                                    "text_segments": [
                                                        {
                                                            "start_index": 7,
                                                            "end_index": 11,
                                                        }
                                                    ]
                                                }
                                            }
                                        },
                                        {
                                            "layout": {
                                                "text_anchor": {
                                                    "text_segments": [
                                                        {
                                                            "start_index": 11,
                                                            "end_index": 14,
                                                        }
                                                    ]
                                                }
                                            }
                                        },
                                    ]
                                }
                            ],
                        }
                    ],
                    "form_fields": [
                        {
                            "field_name": {
                                "text_anchor": {
                                    "text_segments": [
                                        {"start_index": 0, "end_index": 7}
                                    ]
                                }
                            },
                            "field_value": {
                                "text_anchor": {
                                    "text_segments": [
                                        {"start_index": 11, "end_index": 14}
                                    ]
                                }
                            },
                            "value_type": "text",
                        }
                    ],
                }
            ],
        )

        normalized = normalize_document(document, "form", "form-id")

        self.assertEqual(normalized.tables[0].header_rows[0].cells[0].text, "Revenue")
        self.assertEqual(normalized.tables[0].body_rows[0].cells[1].text, "100")
        self.assertEqual(normalized.fields[0].key, "Revenue")
        self.assertEqual(normalized.fields[0].value, "100")


class FusionAndChunkingTests(unittest.TestCase):
    def test_merges_duplicate_text_and_suppresses_table_ocr_text(self):
        page = PageInfo(page_number=1, width=100, height=100)
        duplicate_box = BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.2)
        table_box = BoundingBox(left=0.1, top=0.4, right=0.9, bottom=0.8)
        ocr = NormalizedDocument(
            processor_kind="ocr",
            processor_id="ocr-id",
            page_count=1,
            pages=[page],
            blocks=[
                TextBlock(
                    id="ocr-title",
                    page_number=1,
                    text="Revenue summary",
                    bounding_box=duplicate_box,
                    source_processors=["ocr"],
                    source_refs=["ocr-title"],
                ),
                TextBlock(
                    id="ocr-table",
                    page_number=1,
                    text="Revenue 100",
                    bounding_box=table_box,
                    source_processors=["ocr"],
                    source_refs=["ocr-table"],
                ),
            ],
        )
        form = NormalizedDocument(
            processor_kind="form",
            processor_id="form-id",
            page_count=1,
            pages=[page],
            blocks=[
                TextBlock(
                    id="form-title",
                    page_number=1,
                    text="Revenue summary",
                    bounding_box=duplicate_box,
                    source_processors=["form"],
                    source_refs=["form-title"],
                ),
                TextBlock(
                    id="form-table-text",
                    page_number=1,
                    text="Revenue 100",
                    bounding_box=table_box,
                    source_processors=["form"],
                    source_refs=["form-table-text"],
                ),
            ],
            tables=[
                DocumentTable(
                    id="table-1",
                    page_number=1,
                    bounding_box=table_box,
                    source_processors=["form"],
                )
            ],
        )

        unified = fuse_documents(1, "report.pdf", ocr, form)

        title = next(block for block in unified.blocks if block.id == "ocr-title")
        table_text = next(block for block in unified.blocks if block.id == "ocr-table")
        self.assertEqual(title.source_processors, ["ocr", "form"])
        self.assertEqual(table_text.consumed_by, "table-1")
        self.assertEqual(
            len([block for block in unified.blocks if block.text == "Revenue 100"]), 1
        )

    def test_table_chunks_repeat_headers_and_preserve_structured_rows(self):
        headers = TableRow(
            cells=[
                TableCell(text="Metric", row_index=0, column_index=0),
                TableCell(text="2025", row_index=0, column_index=1),
            ]
        )
        rows = [
            TableRow(
                cells=[
                    TableCell(
                        text=f"Metric {index}", row_index=index + 1, column_index=0
                    ),
                    TableCell(
                        text=str(index * 100), row_index=index + 1, column_index=1
                    ),
                ]
            )
            for index in range(12)
        ]
        document = fuse_documents(
            3,
            "report.pdf",
            NormalizedDocument(processor_kind="ocr", processor_id="ocr", page_count=1),
            NormalizedDocument(
                processor_kind="form",
                processor_id="form",
                page_count=1,
                tables=[
                    DocumentTable(
                        id="table-1",
                        page_number=1,
                        title="Financial metrics",
                        header_rows=[headers],
                        body_rows=rows,
                        source_processors=["form"],
                    )
                ],
            ),
        )

        chunks = build_document_chunks(document, "default", "user-1", chunk_size=180)
        table_chunks = [
            chunk for chunk in chunks if chunk["metadata"]["content_type"] == "table"
        ]

        self.assertGreater(len(table_chunks), 1)
        for chunk in table_chunks:
            self.assertIn("Metric", chunk["content"])
            self.assertIn("2025", chunk["content"])
            self.assertIn("structured_data", chunk["metadata"])
            self.assertTrue(chunk["metadata"]["chunk_id"].startswith("file-3-table"))

    def test_header_only_table_builds_chunk_without_body_rows(self):
        headers = TableRow(
            cells=[
                TableCell(text="Metric", row_index=0, column_index=0),
                TableCell(text="2025", row_index=0, column_index=1),
            ]
        )
        document = fuse_documents(
            4,
            "report.pdf",
            NormalizedDocument(processor_kind="ocr", processor_id="ocr", page_count=1),
            NormalizedDocument(
                processor_kind="form",
                processor_id="form",
                page_count=1,
                tables=[
                    DocumentTable(
                        id="header-only",
                        page_number=1,
                        title="Header only",
                        header_rows=[headers],
                        body_rows=[],
                        source_processors=["form"],
                    )
                ],
            ),
        )

        chunks = build_document_chunks(document, "default", "user-1", chunk_size=180)
        table_chunks = [
            chunk for chunk in chunks if chunk["metadata"]["content_type"] == "table"
        ]

        self.assertEqual(len(table_chunks), 1)
        self.assertIn("| Metric | 2025 |", table_chunks[0]["content"])
        self.assertEqual(table_chunks[0]["metadata"]["structured_data"]["rows"], [])

    def test_chunk_point_id_is_stable_for_structured_chunk_id(self):
        chunk = {
            "content": "value",
            "metadata": {
                "file_id": 3,
                "chunk_index": 7,
                "chunk_id": "file-3-table-table-1-0",
            },
        }

        self.assertEqual(make_chunk_point_id(chunk), make_chunk_point_id(chunk))

    def test_record_processing_failure_preserves_existing_specific_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_dir = Path(temp_dir)
            manifest_path = artifact_dir / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "failed_stage": "fusion",
                        "error_code": "document_fusion_failed",
                        "error": "NameError: name 'body_rows' is not defined",
                    }
                ),
                encoding="utf-8",
            )

            record_processing_failure(
                artifact_dir,
                "fusion",
                "document_fusion_failed",
                "Document fusion failed.",
            )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["error"], "NameError: name 'body_rows' is not defined"
            )


class DocumentProcessingServiceTests(unittest.IsolatedAsyncioTestCase):
    def make_settings(self, artifact_dir: str):
        return SimpleNamespace(
            document_ai_project_id="30831977495",
            document_ai_location="asia-southeast1",
            document_ai_ocr_processor_id="ocr-id",
            document_ai_form_processor_id="form-id",
            document_ai_page_batch_size=15,
            document_ai_batch_concurrency=2,
            document_ai_call_timeout_seconds=120,
            document_ai_total_timeout_seconds=30,
            document_ai_max_pages=200,
            document_ai_artifact_dir=artifact_dir,
            table_stitching_enabled=True,
            table_stitching_min_score=0.75,
        )

    async def test_processes_twenty_pages_with_two_processors_and_writes_artifacts(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeDocumentAIClient(settings.document_ai_form_processor_id)
            service = DocumentProcessingService(settings=settings, client=client)

            result = await service.process_pdf(
                make_pdf(20),
                file_id=9,
                filename="report.pdf",
                assistant_id="default",
                user_id="user-1",
            )

            self.assertEqual(len(client.calls), 4)
            self.assertEqual(
                sorted(page_count for _, page_count in client.calls), [5, 5, 15, 15]
            )
            self.assertEqual(result.unified_document.page_count, 20)
            self.assertEqual(
                sorted(page.page_number for page in result.unified_document.pages),
                list(range(1, 21)),
            )
            for name in (
                "ocr.normalized.json",
                "form.normalized.json",
                "fused.json",
                "table-stitching.json",
                "manifest.json",
            ):
                self.assertTrue((Path(temp_dir) / "9" / name).exists())
            self.assertEqual(result.processing_summary["physical_table_count"], 0)
            self.assertEqual(result.processing_summary["logical_table_count"], 0)
            self.assertEqual(result.processing_summary["stitched_table_count"], 0)

    async def test_processor_failure_is_strict_and_preserves_audit_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeDocumentAIClient(
                settings.document_ai_form_processor_id,
                fail_form=True,
            )
            service = DocumentProcessingService(settings=settings, client=client)

            with self.assertRaises(DocumentProcessingError):
                await service.process_pdf(
                    make_pdf(2),
                    file_id=10,
                    filename="report.pdf",
                    assistant_id="default",
                    user_id="user-1",
                )

            artifact_dir = Path(temp_dir) / "10"
            self.assertTrue((artifact_dir / "ocr.normalized.json").exists())
            self.assertTrue((artifact_dir / "form.normalized.json").exists())
            manifest = json.loads((artifact_dir / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["failed_stage"], "document_ai")

    async def test_table_stitching_failure_falls_back_and_document_stays_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            client = FakeDocumentAIClient(settings.document_ai_form_processor_id)
            service = DocumentProcessingService(settings=settings, client=client)

            with patch(
                "app.document_processing.table_stitching.stitch_tables",
                side_effect=RuntimeError("stitch rule failed"),
            ):
                result = await service.process_pdf(
                    make_pdf(1),
                    file_id=12,
                    filename="report.pdf",
                    assistant_id="default",
                    user_id="user-1",
                )

            self.assertEqual(result.processing_summary["status"], "ready")
            self.assertEqual(result.processing_summary["fusion_warning_count"], 1)
            stitching = json.loads(
                (Path(temp_dir) / "12" / "table-stitching.json").read_text()
            )
            self.assertIn("stitch rule failed", stitching["warnings"][0])

    async def test_rejects_pdf_over_page_limit_before_processor_calls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.make_settings(temp_dir)
            settings.document_ai_max_pages = 1
            client = FakeDocumentAIClient(settings.document_ai_form_processor_id)
            service = DocumentProcessingService(settings=settings, client=client)

            with self.assertRaises(DocumentProcessingError) as raised:
                await service.process_pdf(
                    make_pdf(2),
                    file_id=11,
                    filename="report.pdf",
                    assistant_id="default",
                    user_id="user-1",
                )

            self.assertEqual(raised.exception.status_code, 413)
            self.assertEqual(client.calls, [])


class UploadIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def file_record(self, file_id: int, status: str) -> dict:
        now = datetime.now()
        return {
            "id": file_id,
            "user_id": "user-1",
            "assistant_id": "default",
            "original_name": "report.pdf",
            "saved_name": "saved_report.pdf",
            "file_path": "/tmp/saved_report.pdf",
            "content_type": "application/pdf",
            "size_bytes": 100,
            "status": status,
            "page_count": 1 if status == "ready" else None,
            "chunk_count": 1 if status == "ready" else 0,
            "artifact_dir": None,
            "processing_error": None,
            "created_at": now,
            "updated_at": now,
        }

    async def test_index_failure_deletes_partial_qdrant_points_and_marks_file_failed(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_dir = Path(temp_dir) / "processed" / "41"
            artifact_dir.mkdir(parents=True)
            chunks = [
                {
                    "content": "financial text",
                    "metadata": {
                        "assistant_id": "default",
                        "file_id": 41,
                        "chunk_index": 0,
                    },
                }
            ]
            result = DocumentProcessingResult(
                unified_document=UnifiedDocument(
                    file_id=41,
                    filename="report.pdf",
                    page_count=1,
                ),
                chunks=chunks,
                processing_summary={
                    "status": "ready",
                    "page_count": 1,
                    "chunk_count": 1,
                },
                artifact_dir=artifact_dir,
            )
            service = SimpleNamespace()

            async def process_pdf(**kwargs):
                return result

            service.process_pdf = process_pdf
            settings = SimpleNamespace(
                document_ai_enabled=True,
                document_ai_max_file_bytes=1024 * 1024,
            )
            upload = UploadFile(filename="report.pdf", file=BytesIO(make_pdf(1)))
            updates = []

            def update_record(file_id, status, **kwargs):
                updates.append((file_id, status, kwargs))
                return self.file_record(file_id, status)

            with (
                patch("app.uploads.UPLOAD_DIR", Path(temp_dir) / "uploads"),
                patch(
                    "app.uploads.save_file_record",
                    return_value=self.file_record(41, "processing"),
                ),
                patch("app.uploads.update_file_processing", side_effect=update_record),
                patch("app.uploads.get_settings", return_value=settings),
                patch(
                    "app.uploads.get_document_processing_service", return_value=service
                ),
                patch(
                    "app.uploads.add_chunks_to_vectorstore",
                    side_effect=RuntimeError("qdrant unavailable"),
                ),
                patch("app.uploads.delete_file_chunks") as delete_chunks,
            ):
                with self.assertRaises(Exception):
                    await upload_file(upload, user={"id": "user-1"})

            delete_chunks.assert_called_once_with("user-1", 41)
            self.assertEqual(updates[-1][1], "failed")

    async def test_non_pdf_keeps_local_parser_flow(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = SimpleNamespace(document_ai_enabled=True)
            upload = UploadFile(filename="notes.txt", file=BytesIO(b"financial notes"))

            def update_record(file_id, status, **kwargs):
                record = self.file_record(file_id, status)
                record["original_name"] = "notes.txt"
                record["content_type"] = "text/plain"
                record["page_count"] = kwargs.get("page_count")
                record["chunk_count"] = kwargs.get("chunk_count") or 0
                return record

            with (
                patch("app.uploads.UPLOAD_DIR", Path(temp_dir) / "uploads"),
                patch(
                    "app.uploads.save_file_record",
                    return_value=self.file_record(42, "processing"),
                ),
                patch("app.uploads.update_file_processing", side_effect=update_record),
                patch("app.uploads.get_settings", return_value=settings),
                patch("app.uploads.add_chunks_to_vectorstore"),
                patch("app.uploads.get_document_processing_service") as get_service,
            ):
                result = await upload_file(upload, user={"id": "user-1"})

            get_service.assert_not_called()
            self.assertEqual(result["file"]["status"], "ready")
            self.assertEqual(result["processing_summary"]["table_count"], 0)
            self.assertEqual(len(result["chunks"]), 1)
            validated = FileUploadResponse.model_validate(result)
            self.assertEqual(validated.file.status, "ready")


if __name__ == "__main__":
    unittest.main()
