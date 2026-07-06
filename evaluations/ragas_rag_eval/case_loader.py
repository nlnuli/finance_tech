from __future__ import annotations

import json
from pathlib import Path

from .models import RagasCase


def split_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def load_cases(
    path: Path,
    limit: int | None = None,
    case_ids: list[str] | None = None,
) -> list[RagasCase]:
    if not path.exists():
        raise FileNotFoundError(f"Ragas case file not found: {path}")

    selected_ids = set(case_ids or [])
    cases: list[RagasCase] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            raw = json.loads(line)
            case = RagasCase(
                id=raw["id"],
                question=raw["question"],
                reference=raw["reference"],
                reference_contexts=list(raw.get("reference_contexts") or []),
                source_files=list(raw.get("source_files") or []),
                metadata=dict(raw.get("metadata") or {}),
            )
            if selected_ids and case.id not in selected_ids:
                continue
            cases.append(case)
            if limit is not None and len(cases) >= limit:
                break

    return cases
