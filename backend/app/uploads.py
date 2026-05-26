from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, UploadFile

from .model.storage import save_file_record
from .parsing import parse_file
from .rag import split_text_into_chunks
from .schemas import FileUploadResponse
from .vectorstore import add_chunks_to_vectorstore


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

    try:
        text = parse_file(file_path)
    except Exception:
        file_path.unlink(missing_ok=True)
        raise

    file_record = save_file_record(
        assistant_id=assistant_id,
        original_name=original_name,
        saved_name=saved_name,
        file_path=str(file_path),
        content_type=file.content_type,
        size_bytes=len(content),
    )

    chunks = split_text_into_chunks(
        text=text,
        filename=original_name,
        assistant_id=assistant_id,
        file_id=file_record["id"],
    )
    add_chunks_to_vectorstore(chunks)

    return {
        "file": file_record,
        "chunks": chunks,
    }
