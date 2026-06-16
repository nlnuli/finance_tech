from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from .document_loader import (
    collect_source_files,
    load_eval_documents,
    load_eval_documents_from_files,
)
from .models import RagasCase
from .ragas_compat import patch_ragas_vertexai_import


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.llm import get_llm  # noqa: E402
from app.vectorstore import get_embeddings  # noqa: E402


def get_sample_value(sample: dict, *keys: str, default=None):
    for key in keys:
        value = sample.get(key)
        if value not in (None, ""):
            return value
    return default


def normalize_reference_contexts(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def is_valid_generated_sample(sample: Any) -> bool:
    if sample is None:
        return False
    if isinstance(sample, float) and math.isnan(sample):
        return False
    return True


def sample_to_dict(sample: Any) -> dict[str, Any]:
    if hasattr(sample, "model_dump"):
        return sample.model_dump(exclude_none=True)
    if isinstance(sample, dict):
        return sample
    return {}


def testset_to_cases(testset, source_files: list[str]) -> list[RagasCase]:
    if hasattr(testset, "to_list"):
        raw_samples = testset.to_list()
    elif hasattr(testset, "to_pandas"):
        raw_samples = testset.to_pandas().to_dict(orient="records")
    else:
        raise TypeError("Unsupported Ragas testset object; expected to_list().")

    cases: list[RagasCase] = []
    for index, sample in enumerate(raw_samples, start=1):
        question = get_sample_value(sample, "user_input", "question")
        reference = get_sample_value(sample, "reference", "ground_truth", "answer")
        if not question or not reference:
            continue

        cases.append(
            RagasCase(
                id=f"ragas_case_{index:04d}_{uuid4().hex[:8]}",
                question=str(question),
                reference=str(reference),
                reference_contexts=normalize_reference_contexts(
                    get_sample_value(sample, "reference_contexts", "contexts", default=[])
                ),
                source_files=source_files,
                metadata={
                    key: value
                    for key, value in sample.items()
                    if key
                    not in {
                        "user_input",
                        "question",
                        "reference",
                        "ground_truth",
                        "answer",
                        "reference_contexts",
                        "contexts",
                    }
                },
            )
        )

    if not cases:
        raise ValueError("Ragas did not generate any usable single-turn QA cases.")

    return cases


def samples_to_cases(samples: list[Any], source_files: list[str]) -> list[RagasCase]:
    raw_samples = [
        sample_to_dict(sample)
        for sample in samples
        if is_valid_generated_sample(sample)
    ]
    raw_samples = [sample for sample in raw_samples if sample]

    cases: list[RagasCase] = []
    for index, sample in enumerate(raw_samples, start=1):
        question = get_sample_value(sample, "user_input", "question")
        reference = get_sample_value(sample, "reference", "ground_truth", "answer")
        if not question or not reference:
            continue

        cases.append(
            RagasCase(
                id=f"ragas_case_{index:04d}_{uuid4().hex[:8]}",
                question=str(question),
                reference=str(reference),
                reference_contexts=normalize_reference_contexts(
                    get_sample_value(sample, "reference_contexts", "contexts", default=[])
                ),
                source_files=source_files,
                metadata={
                    key: value
                    for key, value in sample.items()
                    if key
                    not in {
                        "user_input",
                        "question",
                        "reference",
                        "ground_truth",
                        "answer",
                        "reference_contexts",
                        "contexts",
                    }
                },
            )
        )

    return cases


def write_cases(path: Path, cases: list[RagasCase]) -> None:
    from dataclasses import asdict

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for case in cases:
            file.write(json.dumps(asdict(case), ensure_ascii=False) + "\n")


def generate_cases_from_documents(
    documents,
    case_count: int,
) -> list[RagasCase]:
    patch_ragas_vertexai_import()
    from ragas.testset import TestsetGenerator

    source_files = sorted(
        {
            str(document.metadata.get("source"))
            for document in documents
            if document.metadata.get("source")
        }
    )

    generator = TestsetGenerator.from_langchain(
        llm=get_llm(),
        embedding_model=get_embeddings(),
    )
    executor = generator.generate_with_langchain_docs(
        documents=documents,
        testset_size=case_count,
        raise_exceptions=False,
        return_executor=True,
    )
    samples = executor.results()
    return samples_to_cases(samples, source_files=source_files)


def generate_cases(
    source_paths: list[str],
    case_count: int,
    output_path: Path,
) -> list[RagasCase]:
    documents = load_eval_documents(source_paths)
    cases = generate_cases_from_documents(
        documents=documents,
        case_count=case_count,
    )
    if not cases:
        raise ValueError(
            "Ragas did not generate any usable cases. "
            "Check the LLM output parser errors above or try a smaller source file."
        )
    write_cases(output_path, cases)
    return cases


def refresh_case_ids(cases: list[RagasCase], start_index: int) -> list[RagasCase]:
    refreshed = []
    for offset, case in enumerate(cases):
        refreshed.append(
            RagasCase(
                id=f"ragas_case_{start_index + offset:04d}_{uuid4().hex[:8]}",
                question=case.question,
                reference=case.reference,
                reference_contexts=case.reference_contexts,
                source_files=case.source_files,
                metadata=case.metadata,
            )
        )
    return refreshed


def batched(values: list[Path], batch_size: int) -> list[list[Path]]:
    return [
        values[index : index + batch_size]
        for index in range(0, len(values), batch_size)
    ]


def generate_cases_in_batches(
    source_paths: list[str],
    target_case_count: int,
    output_path: Path,
    batch_size: int,
    cases_per_batch: int,
) -> list[RagasCase]:
    if batch_size <= 0:
        raise ValueError("--batch-size must be greater than 0")
    if cases_per_batch <= 0:
        raise ValueError("--cases-per-batch must be greater than 0")

    all_files = collect_source_files(source_paths)
    if not all_files:
        raise ValueError("No supported evaluation documents found.")

    all_cases: list[RagasCase] = []
    failures: list[tuple[list[str], str]] = []

    for batch_index, file_batch in enumerate(batched(all_files, batch_size), start=1):
        if len(all_cases) >= target_case_count:
            break

        print(
            f"batch {batch_index}: files={len(file_batch)}, "
            f"current_cases={len(all_cases)}/{target_case_count}"
        )
        try:
            documents = load_eval_documents_from_files(file_batch)
            batch_cases = generate_cases_from_documents(
                documents=documents,
                case_count=min(cases_per_batch, target_case_count - len(all_cases)),
            )
        except Exception as exc:
            failures.append(([str(path) for path in file_batch], str(exc)))
            print(f"  batch failed: {exc}")
            continue

        if not batch_cases:
            print("  batch produced 0 usable cases")
            continue

        refreshed = refresh_case_ids(batch_cases, start_index=len(all_cases) + 1)
        all_cases.extend(refreshed)
        write_cases(output_path, all_cases)
        print(f"  batch cases: {len(refreshed)}")

    if failures:
        failure_path = output_path.with_suffix(".failures.json")
        failure_path.write_text(
            json.dumps(
                [
                    {"files": files, "error": error}
                    for files, error in failures
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    if not all_cases:
        raise ValueError(
            "No usable cases were generated from any batch. "
            "Try a smaller --batch-size or a more stable LLM endpoint."
        )

    write_cases(output_path, all_cases[:target_case_count])
    return all_cases[:target_case_count]
