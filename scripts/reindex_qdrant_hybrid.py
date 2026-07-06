import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings  # noqa: E402
from app.document_processing.chunking import build_document_chunks  # noqa: E402
from app.document_processing.models import UnifiedDocument  # noqa: E402
from app.document_processing.table_stitching import (  # noqa: E402
    stitch_tables_fail_open,
)
from app.model.storage import (  # noqa: E402
    get_file_record,
    list_file_records,
    update_file_processing,
)
from app.parsing import parse_file  # noqa: E402
from app.rag import split_text_into_chunks  # noqa: E402
from app.vectorstore import (  # noqa: E402
    add_chunks_to_vectorstore,
    count_file_chunks,
    delete_file_chunks,
    ensure_collection_exists,
)


def artifact_path(file_record: dict, filename: str) -> Path | None:
    artifact_dir = file_record.get("artifact_dir")
    if not artifact_dir:
        return None
    return Path(artifact_dir) / filename


def read_manifest(file_record: dict) -> dict:
    path = artifact_path(file_record, "manifest.json")
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def is_recoverable_index_failure(file_record: dict) -> bool:
    if file_record.get("status") != "failed":
        return False
    fused_path = artifact_path(file_record, "fused.json")
    manifest = read_manifest(file_record)
    return bool(
        fused_path
        and fused_path.exists()
        and manifest.get("failed_stage") == "indexing"
    )


def load_chunks_for_file(
    file_record: dict,
    persist_stitching: bool = False,
) -> tuple[list[dict], int]:
    file_id = int(file_record["id"])
    assistant_id = str(file_record["assistant_id"])
    user_id = str(file_record.get("user_id") or "default")
    filename = str(file_record["original_name"])
    file_path = Path(file_record["file_path"])
    fused_path = artifact_path(file_record, "fused.json")

    if file_path.suffix.lower() == ".pdf" and fused_path and fused_path.exists():
        unified = UnifiedDocument.model_validate_json(
            fused_path.read_text(encoding="utf-8")
        )
        unified.file_id = file_id
        unified.filename = filename
        settings = get_settings()
        table_stitching = stitch_tables_fail_open(
            tables=unified.tables,
            blocks=unified.blocks,
            minimum_score=settings.table_stitching_min_score,
            enabled=settings.table_stitching_enabled,
        )
        chunks = build_document_chunks(
            unified,
            assistant_id,
            user_id,
            logical_tables=table_stitching.logical_tables,
        )
        if persist_stitching:
            stitching_path = artifact_path(file_record, "table-stitching.json")
            if stitching_path:
                write_json_atomic(
                    stitching_path,
                    table_stitching.model_dump(mode="json"),
                )
            manifest_path = artifact_path(file_record, "manifest.json")
            if manifest_path:
                manifest = read_manifest(file_record)
                summary = manifest.setdefault("summary", {})
                summary.update(
                    {
                        "table_count": table_stitching.logical_table_count,
                        "physical_table_count": table_stitching.physical_table_count,
                        "logical_table_count": table_stitching.logical_table_count,
                        "stitched_table_count": table_stitching.stitched_table_count,
                        "chunk_count": len(chunks),
                    }
                )
                artifacts = summary.setdefault("artifacts", {})
                artifacts["table_stitching"] = "table-stitching.json"
                write_json_atomic(manifest_path, manifest)
        return chunks, unified.page_count

    if not file_path.exists():
        raise FileNotFoundError(f"Source file does not exist: {file_path}")
    text = parse_file(file_path)
    chunks = split_text_into_chunks(
        text=text,
        filename=filename,
        assistant_id=assistant_id,
        file_id=file_id,
        user_id=user_id,
    )
    return chunks, 1 if text else 0


def mark_manifest_recovered(file_record: dict) -> None:
    path = artifact_path(file_record, "manifest.json")
    if not path or not path.exists():
        return
    manifest = read_manifest(file_record)
    if not manifest:
        return
    manifest["status"] = "ready"
    if isinstance(manifest.get("summary"), dict):
        manifest["summary"]["status"] = "ready"
    for key in ("failed_stage", "error_code", "error"):
        manifest.pop(key, None)
    write_json_atomic(path, manifest)


def reindex_file(
    file_record: dict,
    target_collection: str,
    retries: int,
    retry_delay: float,
) -> int:
    chunks, page_count = load_chunks_for_file(
        file_record,
        persist_stitching=True,
    )
    user_id = str(file_record.get("user_id") or "default")
    file_id = int(file_record["id"])

    for attempt in range(retries + 1):
        try:
            delete_file_chunks(user_id, file_id, target_collection)
            add_chunks_to_vectorstore(chunks, target_collection)
            indexed_count = count_file_chunks(
                user_id,
                file_id,
                target_collection,
            )
            if indexed_count != len(chunks):
                raise RuntimeError(
                    f"Indexed point count is {indexed_count}; expected {len(chunks)}"
                )
            break
        except Exception:
            try:
                delete_file_chunks(user_id, file_id, target_collection)
            except Exception:
                pass
            if attempt >= retries:
                raise
            time.sleep(retry_delay * (attempt + 1))

    if file_record.get("status") == "failed":
        mark_manifest_recovered(file_record)
    update_file_processing(
        file_id,
        "ready",
        page_count=page_count,
        chunk_count=len(chunks),
        artifact_dir=file_record.get("artifact_dir"),
        processing_error=None,
    )
    return len(chunks)


def select_file_records(args: argparse.Namespace) -> list[dict]:
    if args.file_id is not None:
        record = get_file_record(args.file_id)
        if not record:
            raise ValueError(f"File record {args.file_id} does not exist")
        if args.assistant_id and record["assistant_id"] != args.assistant_id:
            return []
        return [record]

    statuses = ("ready", "failed") if args.include_recoverable_failed else ("ready",)
    return list_file_records(
        assistant_id=args.assistant_id,
        statuses=statuses,
        after_file_id=args.after_file_id,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild the Qdrant dense + BM25 hybrid collection.",
    )
    parser.add_argument("--assistant-id")
    parser.add_argument("--file-id", type=int)
    parser.add_argument("--after-file-id", type=int)
    parser.add_argument("--target-collection")
    parser.add_argument("--include-recoverable-failed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-delay", type=float, default=2.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    target_collection = args.target_collection or settings.qdrant_collection
    records = select_file_records(args)

    selected = []
    for record in records:
        if record.get("status") == "failed" and not (
            args.include_recoverable_failed and is_recoverable_index_failure(record)
        ):
            continue
        selected.append(record)

    print(f"target collection: {target_collection}")
    print(f"selected files: {len(selected)}")
    if args.dry_run:
        for record in selected:
            chunks, _ = load_chunks_for_file(record)
            print(
                f"file_id={record['id']} name={record['original_name']} "
                f"chunks={len(chunks)} status={record['status']}"
            )
        return

    ensure_collection_exists(target_collection)
    indexed_files = 0
    indexed_chunks = 0
    failures = []
    for record in selected:
        print(f"reindexing file_id={record['id']} {record['original_name']} ...")
        try:
            chunk_count = reindex_file(
                record,
                target_collection,
                retries=max(0, args.retries),
                retry_delay=max(0.0, args.retry_delay),
            )
        except Exception as exc:
            failures.append((record["id"], record["original_name"], str(exc)))
            print(f"  failed: {exc}")
            continue
        indexed_files += 1
        indexed_chunks += chunk_count
        print(f"  indexed chunks: {chunk_count}")

    print(f"indexed files: {indexed_files}")
    print(f"indexed chunks: {indexed_chunks}")
    print(f"failed files: {len(failures)}")
    for file_id, filename, error in failures:
        print(f"- file_id={file_id} {filename}: {error}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
