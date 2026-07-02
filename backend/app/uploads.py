import asyncio
from pathlib import Path
import time
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .config import get_settings
from .document_processing import (
    DocumentProcessingError,
    get_document_processing_service,
)
from .document_processing.service import record_processing_failure
from .model.storage import save_file_record, update_file_processing
from .parsing import parse_file
from .rag import split_text_into_chunks
from .schemas import FileUploadResponse
from .vectorstore import add_chunks_to_vectorstore, delete_file_chunks

router = APIRouter(prefix="/api/files", tags=["files"])

UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
DEFAULT_ASSISTANT_ID = "default"


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    assistant_id: str = Form(DEFAULT_ASSISTANT_ID),
) -> dict:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    original_name = file.filename or "uploaded_file"
    saved_name = f"{uuid4().hex}_{Path(original_name).name}"
    file_path = UPLOAD_DIR / saved_name

    content = await file.read()
    file_path.write_bytes(content)
    file_record = save_file_record(
        assistant_id=assistant_id,
        original_name=original_name,
        saved_name=saved_name,
        file_path=str(file_path),
        content_type=file.content_type,
        size_bytes=len(content),
        status="processing",
    )
    file_id = file_record["id"]
    artifact_dir = None
    indexing_started = False

    async def mark_failed(stage: str, error_code: str, message: str) -> None:
        if indexing_started:
            try:
                await asyncio.to_thread(delete_file_chunks, assistant_id, file_id)
            except Exception:
                pass
        try:
            record_processing_failure(artifact_dir, stage, error_code, message)
        except Exception:
            pass
        try:
            await asyncio.to_thread(
                update_file_processing,
                file_id,
                "failed",
                artifact_dir=str(artifact_dir) if artifact_dir else None,
                processing_error=message[:1000],
            )
        except Exception:
            pass

    try:
        extension = file_path.suffix.lower()
        settings = get_settings()
        if extension == ".pdf" and settings.document_ai_enabled:
            if len(content) > settings.document_ai_max_file_bytes:
                raise DocumentProcessingError(
                    stage="validation",
                    error_code="pdf_file_limit_exceeded",
                    message=(
                        f"PDF size exceeds {settings.document_ai_max_file_bytes} bytes."
                    ),
                    status_code=413,
                )
            processing_result = await get_document_processing_service().process_pdf(
                content=content,
                file_id=file_id,
                filename=original_name,
                assistant_id=assistant_id,
            )
            chunks = processing_result.chunks
            processing_summary = processing_result.processing_summary
            artifact_dir = processing_result.artifact_dir
            page_count = processing_result.unified_document.page_count
        else:
            started_at = time.perf_counter()
            text = await asyncio.to_thread(parse_file, file_path)
            chunks = split_text_into_chunks(
                text=text,
                filename=original_name,
                assistant_id=assistant_id,
                file_id=file_id,
            )
            page_count = 1 if text else 0
            processing_summary = {
                "status": "ready",
                "page_count": page_count,
                "chunk_count": len(chunks),
                "text_block_count": len(chunks),
                "table_count": 0,
                "physical_table_count": 0,
                "logical_table_count": 0,
                "stitched_table_count": 0,
                "form_field_count": 0,
                "fusion_warning_count": 0,
                "duration_seconds": time.perf_counter() - started_at,
                "artifacts": {},
            }

        indexing_started = True
        await asyncio.to_thread(add_chunks_to_vectorstore, chunks)
        file_record = await asyncio.to_thread(
            update_file_processing,
            file_id,
            "ready",
            page_count=page_count,
            chunk_count=len(chunks),
            artifact_dir=str(artifact_dir) if artifact_dir else None,
            processing_error=None,
        )
        return {
            "file": file_record,
            "chunks": chunks,
            "processing_summary": processing_summary,
        }
    except DocumentProcessingError as exc:
        artifact_dir = exc.artifact_dir or artifact_dir
        await mark_failed(exc.stage, exc.error_code, str(exc))
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "error": exc.error_code,
                "file_id": file_id,
                "status": "failed",
                "stage": exc.stage,
            },
        ) from exc
    except HTTPException as exc:
        await mark_failed("validation", "upload_validation_failed", str(exc.detail))
        raise
    except Exception as exc:
        await mark_failed(
            "indexing" if indexing_started else "processing",
            (
                "document_indexing_failed"
                if indexing_started
                else "document_processing_failed"
            ),
            f"{exc.__class__.__name__}: {str(exc)[:800]}",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": (
                    "document_indexing_failed"
                    if indexing_started
                    else "document_processing_failed"
                ),
                "file_id": file_id,
                "status": "failed",
                "stage": "indexing" if indexing_started else "processing",
            },
        ) from exc
