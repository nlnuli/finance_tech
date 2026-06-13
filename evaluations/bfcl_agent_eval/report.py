from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Any

import pandas as pd

from .models import CaseScore


def average(values: list[float]) -> float:
    if not values:
        return 0.0
    return mean(values)


def summarize_scores(scores: list[CaseScore]) -> dict[str, Any]:
    categories = sorted({score.category for score in scores})
    by_category = {}

    for category in categories:
        category_scores = [score for score in scores if score.category == category]
        no_call_scores = [
            score.no_call_correct
            for score in category_scores
            if score.no_call_correct is not None
        ]
        by_category[category] = summarize_group(category_scores, no_call_scores)

    all_no_call_scores = [
        score.no_call_correct
        for score in scores
        if score.no_call_correct is not None
    ]
    return {
        "overall": summarize_group(scores, all_no_call_scores),
        "by_category": by_category,
    }


def summarize_group(
    scores: list[CaseScore],
    no_call_scores: list[bool],
) -> dict[str, Any]:
    if not scores:
        return {
            "case_count": 0,
            "overall_accuracy": 0.0,
            "tool_name_accuracy": 0.0,
            "argument_key_accuracy": 0.0,
            "argument_value_accuracy": 0.0,
            "no_call_accuracy": None,
            "avg_latency_seconds": 0.0,
            "failure_count": 0,
        }

    return {
        "case_count": len(scores),
        "overall_accuracy": average([float(score.exact_match) for score in scores]),
        "tool_name_accuracy": average([score.tool_name_accuracy for score in scores]),
        "argument_key_accuracy": average(
            [score.argument_key_accuracy for score in scores]
        ),
        "argument_value_accuracy": average(
            [score.argument_value_accuracy for score in scores]
        ),
        "no_call_accuracy": (
            average([float(value) for value in no_call_scores])
            if no_call_scores
            else None
        ),
        "avg_latency_seconds": average(
            [score.latency_seconds for score in scores]
        ),
        "failure_count": sum(1 for score in scores if score.error),
    }


def summary_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [{"category": "overall", **summary["overall"]}]
    for category, metrics in summary["by_category"].items():
        rows.append({"category": category, **metrics})
    return rows


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_details(path: Path, scores: list[CaseScore]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for score in scores:
            file.write(json.dumps(asdict(score), ensure_ascii=False) + "\n")


def format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def write_markdown_report(
    path: Path,
    summary: dict[str, Any],
    scores: list[CaseScore],
) -> None:
    lines = [
        "# BFCL ReAct Agent Evaluation",
        "",
        "## Summary",
        "",
        "| Category | Cases | Overall | Tool Name | Arg Key | Arg Value | No Call | Avg Latency | Failures |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for row in summary_rows(summary):
        lines.append(
            "| {category} | {case_count} | {overall_accuracy} | "
            "{tool_name_accuracy} | {argument_key_accuracy} | "
            "{argument_value_accuracy} | {no_call_accuracy} | "
            "{avg_latency_seconds:.2f}s | {failure_count} |".format(
                category=row["category"],
                case_count=row["case_count"],
                overall_accuracy=format_percent(row["overall_accuracy"]),
                tool_name_accuracy=format_percent(row["tool_name_accuracy"]),
                argument_key_accuracy=format_percent(row["argument_key_accuracy"]),
                argument_value_accuracy=format_percent(row["argument_value_accuracy"]),
                no_call_accuracy=format_percent(row["no_call_accuracy"]),
                avg_latency_seconds=row["avg_latency_seconds"],
                failure_count=row["failure_count"],
            )
        )

    failures = [score for score in scores if not score.exact_match][:20]
    lines.extend(["", "## First Failed Cases", ""])
    if not failures:
        lines.append("No failed cases.")
    else:
        for score in failures:
            lines.extend(
                [
                    f"### {score.id}",
                    "",
                    f"- Category: `{score.category}`",
                    f"- Error: `{score.error}`",
                    f"- Expected: `{json.dumps(score.expected_calls, ensure_ascii=False)}`",
                    f"- Actual: `{json.dumps(score.actual_calls, ensure_ascii=False)}`",
                    "",
                ]
            )

    path.write_text("\n".join(lines), encoding="utf-8")


def write_reports(output_dir: Path, scores: list[CaseScore]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_scores(scores)
    write_json(output_dir / "summary.json", summary)
    write_details(output_dir / "details.jsonl", scores)
    pd.DataFrame(summary_rows(summary)).to_csv(output_dir / "summary.csv", index=False)
    write_markdown_report(output_dir / "report.md", summary, scores)
    return summary
