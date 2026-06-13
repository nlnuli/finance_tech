from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import BFCLCase, ExpectedCall


VERSION_PREFIX = "BFCL_v4"


def get_bfcl_data_root() -> Path:
    try:
        import bfcl_eval
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "bfcl-eval is not installed. Run: "
            ".venv/bin/pip install -r evaluations/requirements.txt"
        ) from exc

    return Path(bfcl_eval.__file__).resolve().parent / "data"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def parse_expected_calls(raw_answer: dict[str, Any] | None) -> list[ExpectedCall]:
    if not raw_answer:
        return []

    expected_calls: list[ExpectedCall] = []
    for call in raw_answer.get("ground_truth", []):
        for name, arguments in call.items():
            expected_calls.append(ExpectedCall(name=name, arguments=arguments))
    return expected_calls


def first_turn_messages(entry: dict[str, Any]) -> list[dict[str, str]]:
    question = entry.get("question", [])
    if not question:
        return []

    turn = question[0]
    if not isinstance(turn, list):
        return []

    return [
        {
            "role": str(message.get("role", "user")),
            "content": str(message.get("content", "")),
        }
        for message in turn
        if isinstance(message, dict)
    ]


def load_category_cases(
    category: str,
    limit: int | None = None,
    run_ids: set[str] | None = None,
) -> list[BFCLCase]:
    data_root = get_bfcl_data_root()
    question_path = data_root / f"{VERSION_PREFIX}_{category}.json"
    if not question_path.exists():
        raise FileNotFoundError(f"BFCL category file not found: {question_path}")

    answer_path = data_root / "possible_answer" / f"{VERSION_PREFIX}_{category}.json"
    answers_by_id: dict[str, dict[str, Any]] = {}
    if answer_path.exists():
        answers_by_id = {entry["id"]: entry for entry in load_jsonl(answer_path)}

    cases: list[BFCLCase] = []
    for entry in load_jsonl(question_path):
        case_id = entry["id"]
        if run_ids and case_id not in run_ids:
            continue

        cases.append(
            BFCLCase(
                id=case_id,
                category=category,
                messages=first_turn_messages(entry),
                functions=entry.get("function", []),
                expected_calls=parse_expected_calls(answers_by_id.get(case_id)),
            )
        )

        if limit is not None and len(cases) >= limit:
            break

    return cases


def load_cases(
    categories: list[str],
    limit_per_category: int | None,
    run_ids: list[str] | None = None,
) -> list[BFCLCase]:
    run_id_set = set(run_ids or [])
    cases: list[BFCLCase] = []
    for category in categories:
        cases.extend(
            load_category_cases(
                category=category,
                limit=None if run_id_set else limit_per_category,
                run_ids=run_id_set or None,
            )
        )
    return cases
