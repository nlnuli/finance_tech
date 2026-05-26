import argparse
import shutil
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.model.storage import save_file_record
from backend.app.parsing import SUPPORTED_EXTENSIONS, parse_file
from backend.app.rag import split_text_into_chunks
from backend.app.vectorstore import add_chunks_to_vectorstore


UPLOAD_DIR = PROJECT_ROOT / "backend" / "uploads"
DEFAULT_SOURCE_DIR = Path(
    "/Users/yewen/Desktop/mag7_avgo_official_financials_2022_2025_v2/downloaded_files"
)


def get_supported_files(source_dir: Path) -> list[Path]:
    files = []

    for path in sorted(source_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        files.append(path)

    return files


def import_one_file(source_file: Path, assistant_id: str) -> int:
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
        content_type=None,
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import local files into MySQL and Qdrant.",
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
    args = parser.parse_args()

    source_dir = args.source_dir.expanduser().resolve()
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    files = get_supported_files(source_dir)
    print(f"source dir: {source_dir}")
    print(f"supported files: {len(files)}")

    total_chunks = 0
    failed = []

    for index, source_file in enumerate(files, start=1):
        print(f"[{index}/{len(files)}] importing {source_file.name} ...")
        try:
            chunk_count = import_one_file(source_file, args.assistant_id)
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
