import argparse
import mimetypes
import shutil
import sys
import time
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.parsing import SUPPORTED_EXTENSIONS, parse_file


UPLOAD_DIR = PROJECT_ROOT / "backend" / "uploads"
DEFAULT_SOURCE_DIR = Path("/Users/yewen/Desktop/file")


def is_hidden_path(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def get_supported_files(source_dir: Path, recursive: bool = True) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    files = []

    for path in sorted(source_dir.glob(pattern)):
        if not path.is_file():
            continue
        if is_hidden_path(path.relative_to(source_dir)):
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        files.append(path)

    return files


def import_one_file(source_file: Path, assistant_id: str) -> int:
    from app.model.storage import save_file_record
    from app.rag import split_text_into_chunks
    from app.vectorstore import add_chunks_to_vectorstore

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    saved_name = f"{uuid4().hex}_{source_file.name}"
    saved_path = UPLOAD_DIR / saved_name
    shutil.copy2(source_file, saved_path)

    try:
        text = parse_file(saved_path)
    except Exception:
        saved_path.unlink(missing_ok=True)
        raise

    file_record = save_file_record(
        assistant_id=assistant_id,
        original_name=source_file.name,
        saved_name=saved_name,
        file_path=str(saved_path),
        content_type=mimetypes.guess_type(source_file.name)[0],
        size_bytes=saved_path.stat().st_size,
    )

    chunks = split_text_into_chunks(
        text=text,
        filename=source_file.name,
        assistant_id=assistant_id,
        file_id=file_record["id"],
    )
    add_chunks_to_vectorstore(chunks)

    return len(chunks)


def import_one_file_with_retry(
    source_file: Path,
    assistant_id: str,
    retries: int,
    retry_delay: float,
) -> int:
    attempt = 0
    while True:
        try:
            return import_one_file(source_file, assistant_id)
        except Exception:
            attempt += 1
            if attempt > retries:
                raise
            wait_seconds = retry_delay * attempt
            print(
                f"  retrying after transient failure "
                f"({attempt}/{retries}) in {wait_seconds:.1f}s ..."
            )
            time.sleep(wait_seconds)


def format_supported_extensions() -> str:
    return ", ".join(sorted(SUPPORTED_EXTENSIONS))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Import local files into MySQL and Qdrant using the same "
            "parse/split/embed flow as the upload API."
        ),
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="Directory containing files to import.",
    )
    parser.add_argument(
        "--assistant-id",
        default="default",
        help="assistant_id saved in file records and chunk metadata.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Import at most this many supported files.",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Only scan files directly under --source-dir.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list files that would be imported; do not write MySQL/Qdrant.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Retry failed file imports this many times.",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=5.0,
        help="Base delay in seconds between retries. Delay increases per attempt.",
    )
    args = parser.parse_args()

    source_dir = args.source_dir.expanduser().resolve()
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")
    if not source_dir.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {source_dir}")

    files = get_supported_files(source_dir, recursive=not args.no_recursive)
    if args.limit is not None:
        files = files[: args.limit]

    print(f"source dir: {source_dir}")
    print(f"assistant id: {args.assistant_id}")
    print(f"supported extensions: {format_supported_extensions()}")
    print(f"supported files: {len(files)}")

    if args.dry_run:
        for index, source_file in enumerate(files, start=1):
            print(f"[{index}/{len(files)}] {source_file}")
        print("dry run complete; no files were imported.")
        return

    total_chunks = 0
    failed = []

    for index, source_file in enumerate(files, start=1):
        print(f"[{index}/{len(files)}] importing {source_file.name} ...")
        try:
            chunk_count = import_one_file_with_retry(
                source_file=source_file,
                assistant_id=args.assistant_id,
                retries=args.retries,
                retry_delay=args.retry_delay,
            )
        except Exception as exc:
            failed.append((source_file.name, str(exc)))
            print(f"  failed: {exc}")
            continue

        total_chunks += chunk_count
        print(f"  chunks: {chunk_count}")

    print("done")
    print(f"imported files: {len(files) - len(failed)}")
    print(f"failed files: {len(failed)}")
    print(f"total chunks: {total_chunks}")

    if failed:
        print("failures:")
        for filename, error in failed:
            print(f"- {filename}: {error}")


if __name__ == "__main__":
    main()
