from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import get_settings
from .chunking import build_document_chunks
from .client import (
    DocumentAIClient,
    PdfBatch,
    ProcessorCallResult,
    get_pdf_page_count,
    split_pdf_batches,
)
from .fusion import fuse_documents
from .models import NormalizedDocument, TableStitchingResult, UnifiedDocument
from .normalize import (
    get_document_processor_version,
    merge_normalized_documents,
    normalize_document,
)
from .table_stitching import stitch_tables_fail_open


@dataclass
class DocumentProcessingResult:
    unified_document: UnifiedDocument
    chunks: list[dict]
    processing_summary: dict[str, Any]
    artifact_dir: Path
    table_stitching: TableStitchingResult | None = None


class DocumentProcessingError(RuntimeError):
    def __init__(
        self,
        stage: str,
        error_code: str,
        message: str,
        artifact_dir: Path | None = None,
        status_code: int = 502,
    ):
        super().__init__(message)
        self.stage = stage
        self.error_code = error_code
        self.artifact_dir = artifact_dir
        self.status_code = status_code


@dataclass
class BatchOutcome:
    batch: PdfBatch
    ocr: ProcessorCallResult | Exception
    form: ProcessorCallResult | Exception


def _safe_error_message(exc: Exception) -> str:
    message = re.sub(
        r"(?i)(authorization|api[_-]?key|token)=?\s*[^\s,;]+",
        r"\1=<redacted>",
        str(exc),
    )
    return f"{exc.__class__.__name__}: {message}"[:1000]


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def record_processing_failure(
    artifact_dir: Path | str | None,
    stage: str,
    error_code: str,
    message: str,
) -> None:
    if not artifact_dir:
        return
    path = Path(artifact_dir) / "manifest.json"
    manifest = {}
    if path.exists():
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
    manifest.update(
        {
            "status": "failed",
            "failed_stage": stage,
            "error_code": error_code,
            "error": message[:1000],
        }
    )
    _atomic_write_json(path, manifest)


class DocumentProcessingService:
    def __init__(self, settings=None, client: DocumentAIClient | None = None):
        self.settings = settings or get_settings()
        self.client = client or DocumentAIClient(
            project_id=self.settings.document_ai_project_id,
            location=self.settings.document_ai_location,
            call_timeout_seconds=self.settings.document_ai_call_timeout_seconds,
            retry_attempts=3,
        )

    async def _process_batch(
        self,
        batch: PdfBatch,
        semaphore: asyncio.Semaphore,
    ) -> BatchOutcome:
        async with semaphore:
            ocr, form = await asyncio.gather(
                self.client.process(
                    self.settings.document_ai_ocr_processor_id,
                    batch.content,
                ),
                self.client.process(
                    self.settings.document_ai_form_processor_id,
                    batch.content,
                ),
                return_exceptions=True,
            )
        return BatchOutcome(batch=batch, ocr=ocr, form=form)

    def _normalize_outcomes(
        self,
        outcomes: list[BatchOutcome],
    ) -> tuple[NormalizedDocument, NormalizedDocument, list[dict], list[dict]]:
        ocr_documents = []
        form_documents = []
        errors = []
        call_stats = []

        for outcome in outcomes:
            for processor_kind, result, processor_id in (
                (
                    "ocr",
                    outcome.ocr,
                    self.settings.document_ai_ocr_processor_id,
                ),
                (
                    "form",
                    outcome.form,
                    self.settings.document_ai_form_processor_id,
                ),
            ):
                if isinstance(result, Exception):
                    errors.append(
                        {
                            "processor": processor_kind,
                            "start_page": outcome.batch.start_page,
                            "end_page": outcome.batch.end_page,
                            "error": _safe_error_message(result),
                        }
                    )
                    continue

                normalized = normalize_document(
                    result.document,
                    processor_kind=processor_kind,
                    processor_id=processor_id,
                    page_offset=outcome.batch.start_page - 1,
                    processor_version=get_document_processor_version(result.document),
                )
                if processor_kind == "ocr":
                    ocr_documents.append(normalized)
                else:
                    form_documents.append(normalized)
                call_stats.append(
                    {
                        "processor": processor_kind,
                        "start_page": outcome.batch.start_page,
                        "end_page": outcome.batch.end_page,
                        "attempts": result.attempts,
                        "duration_seconds": result.duration_seconds,
                        "processor_name": result.processor_name,
                        "processor_version": normalized.processor_version,
                    }
                )

        ocr_errors = [item["error"] for item in errors if item["processor"] == "ocr"]
        form_errors = [item["error"] for item in errors if item["processor"] == "form"]
        return (
            merge_normalized_documents(
                ocr_documents,
                "ocr",
                self.settings.document_ai_ocr_processor_id,
                ocr_errors,
            ),
            merge_normalized_documents(
                form_documents,
                "form",
                self.settings.document_ai_form_processor_id,
                form_errors,
            ),
            errors,
            call_stats,
        )

    async def process_pdf(
        self,
        content: bytes,
        file_id: int,
        filename: str,
        assistant_id: str,
    ) -> DocumentProcessingResult:
        artifact_dir = Path(self.settings.document_ai_artifact_dir) / str(file_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        started_at = time.perf_counter()

        try:
            page_count = get_pdf_page_count(content)
        except Exception as exc:
            record_processing_failure(
                artifact_dir,
                "validation",
                "invalid_pdf",
                _safe_error_message(exc),
            )
            raise DocumentProcessingError(
                "validation",
                "invalid_pdf",
                "The uploaded PDF could not be read.",
                artifact_dir,
                status_code=400,
            ) from exc

        if page_count > self.settings.document_ai_max_pages:
            message = (
                f"PDF has {page_count} pages; maximum is "
                f"{self.settings.document_ai_max_pages}."
            )
            record_processing_failure(
                artifact_dir, "validation", "pdf_page_limit_exceeded", message
            )
            raise DocumentProcessingError(
                "validation",
                "pdf_page_limit_exceeded",
                message,
                artifact_dir,
                status_code=413,
            )

        try:
            batches = split_pdf_batches(
                content,
                page_batch_size=self.settings.document_ai_page_batch_size,
            )
        except Exception as exc:
            record_processing_failure(
                artifact_dir,
                "batching",
                "pdf_batching_failed",
                _safe_error_message(exc),
            )
            raise DocumentProcessingError(
                "batching",
                "pdf_batching_failed",
                str(exc),
                artifact_dir,
                status_code=413,
            ) from exc

        semaphore = asyncio.Semaphore(self.settings.document_ai_batch_concurrency)
        try:
            outcomes = await asyncio.wait_for(
                asyncio.gather(
                    *(self._process_batch(batch, semaphore) for batch in batches)
                ),
                timeout=self.settings.document_ai_total_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            message = "Document AI processing exceeded the total timeout."
            record_processing_failure(
                artifact_dir, "document_ai", "document_ai_timeout", message
            )
            raise DocumentProcessingError(
                "document_ai",
                "document_ai_timeout",
                message,
                artifact_dir,
            ) from exc

        ocr, form, errors, call_stats = self._normalize_outcomes(outcomes)
        _atomic_write_json(
            artifact_dir / "ocr.normalized.json", ocr.model_dump(mode="json")
        )
        _atomic_write_json(
            artifact_dir / "form.normalized.json", form.model_dump(mode="json")
        )

        manifest = {
            "status": "processing",
            "file_id": file_id,
            "filename": filename,
            "page_count": page_count,
            "batch_count": len(batches),
            "project_id": self.settings.document_ai_project_id,
            "location": self.settings.document_ai_location,
            "ocr_processor_id": self.settings.document_ai_ocr_processor_id,
            "form_processor_id": self.settings.document_ai_form_processor_id,
            "calls": call_stats,
            "errors": errors,
        }
        _atomic_write_json(artifact_dir / "manifest.json", manifest)

        if errors:
            message = "One or more Document AI processor calls failed."
            record_processing_failure(
                artifact_dir, "document_ai", "document_ai_processor_failed", message
            )
            raise DocumentProcessingError(
                "document_ai",
                "document_ai_processor_failed",
                message,
                artifact_dir,
            )

        try:
            unified = fuse_documents(file_id, filename, ocr, form)
            _atomic_write_json(
                artifact_dir / "fused.json", unified.model_dump(mode="json")
            )
            table_stitching = stitch_tables_fail_open(
                tables=unified.tables,
                blocks=unified.blocks,
                minimum_score=self.settings.table_stitching_min_score,
                enabled=self.settings.table_stitching_enabled,
            )
            _atomic_write_json(
                artifact_dir / "table-stitching.json",
                table_stitching.model_dump(mode="json"),
            )
            chunks = build_document_chunks(
                unified,
                assistant_id,
                logical_tables=table_stitching.logical_tables,
            )
        except Exception as exc:
            record_processing_failure(
                artifact_dir,
                "fusion",
                "document_fusion_failed",
                _safe_error_message(exc),
            )
            raise DocumentProcessingError(
                "fusion",
                "document_fusion_failed",
                "Document fusion failed.",
                artifact_dir,
                status_code=500,
            ) from exc

        summary = {
            "status": "ready",
            "ocr_processor_id": self.settings.document_ai_ocr_processor_id,
            "form_processor_id": self.settings.document_ai_form_processor_id,
            "page_count": page_count,
            "text_block_count": len(
                [block for block in unified.blocks if not block.consumed_by]
            ),
            "table_count": table_stitching.logical_table_count,
            "physical_table_count": table_stitching.physical_table_count,
            "logical_table_count": table_stitching.logical_table_count,
            "stitched_table_count": table_stitching.stitched_table_count,
            "form_field_count": len(unified.fields),
            "chunk_count": len(chunks),
            "fusion_warning_count": (
                len(unified.fusion_warnings) + len(table_stitching.warnings)
            ),
            "duration_seconds": time.perf_counter() - started_at,
            "artifacts": {
                "ocr": "ocr.normalized.json",
                "form": "form.normalized.json",
                "fused": "fused.json",
                "table_stitching": "table-stitching.json",
                "manifest": "manifest.json",
            },
        }
        manifest.update({"status": "ready", "summary": summary})
        _atomic_write_json(artifact_dir / "manifest.json", manifest)
        return DocumentProcessingResult(
            unified,
            chunks,
            summary,
            artifact_dir,
            table_stitching,
        )


@lru_cache(maxsize=1)
def get_document_processing_service() -> DocumentProcessingService:
    return DocumentProcessingService()
