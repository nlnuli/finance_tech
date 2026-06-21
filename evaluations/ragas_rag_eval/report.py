from __future__ import annotations

import json
from dataclasses import asdict
from math import isfinite
from pathlib import Path
from statistics import mean
from typing import Any

import pandas as pd

from .models import CaseScore


def average(values: list[float]) -> float:
    if not values:
        return 0.0
    return mean(values)


def average_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return mean(values)


def is_valid_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and isfinite(float(value))


def numeric_metric_values(scores: list[CaseScore], key: str) -> list[float]:
    values = []
    for score in scores:
        value = score.ragas_metrics.get(key)
        if is_valid_number(value):
            values.append(float(value))
    return values


def metric_coverage(scores: list[CaseScore], key: str) -> dict[str, Any]:
    valid_count = len(numeric_metric_values(scores, key))
    total_count = len(scores)
    return {
        "valid_count": valid_count,
        "missing_count": total_count - valid_count,
        "valid_rate": valid_count / total_count if total_count else 0.0,
    }


def bool_metric_average(scores: list[CaseScore], key: str) -> float:
    values = [
        float(score.custom_metrics.get(key))
        for score in scores
        if isinstance(score.custom_metrics.get(key), bool)
    ]
    return average(values)


def summarize_scores(scores: list[CaseScore]) -> dict[str, Any]:
    ragas_metric_names = sorted(
        {
            key
            for score in scores
            for key, value in score.ragas_metrics.items()
            if is_valid_number(value) or value is None
        }
    )
    ragas_summary = {
        key: average_or_none(numeric_metric_values(scores, key))
        for key in ragas_metric_names
    }
    ragas_coverage = {
        key: metric_coverage(scores, key)
        for key in ragas_metric_names
    }

    return {
        "case_count": len(scores),
        "ragas_metrics": ragas_summary,
        "ragas_metric_coverage": ragas_coverage,
        "custom_metrics": {
            "retrieval_hit_rate": bool_metric_average(
                scores, "direct_retrieval_hit"
            ),
            "agent_retrieval_hit_rate": bool_metric_average(
                scores, "agent_retrieval_hit"
            ),
            "rag_tool_use_rate": bool_metric_average(scores, "rag_tool_used"),
            "empty_retrieval_rate": bool_metric_average(scores, "empty_retrieval"),
            "avg_retrieved_context_count": average(
                [
                    float(score.custom_metrics.get("retrieved_context_count") or 0)
                    for score in scores
                ]
            ),
            "avg_direct_retrieved_context_count": average(
                [
                    float(
                        score.custom_metrics.get(
                            "direct_retrieved_context_count"
                        )
                        or 0
                    )
                    for score in scores
                ]
            ),
            "avg_latency_seconds": average(
                [score.latency_seconds for score in scores]
            ),
            "timeout_count": sum(1 for score in scores if score.timed_out),
            "failure_count": sum(1 for score in scores if score.error),
        },
    }


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_details(path: Path, scores: list[CaseScore]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for score in scores:
            file.write(json.dumps(asdict(score), ensure_ascii=False) + "\n")


def flatten_score(score: CaseScore) -> dict[str, Any]:
    row = {
        "id": score.id,
        "question": score.question,
        "reference": score.reference,
        "response": score.response,
        "latency_seconds": score.latency_seconds,
        "error": score.error,
        "timed_out": score.timed_out,
    }
    for key, value in score.ragas_metrics.items():
        row[f"ragas_{key}"] = value
    for key, value in score.custom_metrics.items():
        row[f"custom_{key}"] = value
    return row


def format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def format_score(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.4f}"


def write_markdown_report(
    path: Path,
    summary: dict[str, Any],
    scores: list[CaseScore],
    run_metadata: dict[str, Any] | None = None,
) -> None:
    lines = [
        "# Ragas RAG Evaluation",
        "",
    ]

    if run_metadata:
        lines.extend(
            [
                "## Run Metadata",
                "",
                f"- Run name: `{run_metadata.get('run_name')}`",
                f"- Started at: `{run_metadata.get('started_at')}`",
                f"- Output dir: `{run_metadata.get('output_dir')}`",
                f"- Case file: `{run_metadata.get('case_path')}`",
                f"- Case file SHA256: `{run_metadata.get('case_file_sha256')}`",
                f"- Assistant id: `{run_metadata.get('assistant_id')}`",
                f"- Retrieval k: `{run_metadata.get('retrieval_k')}`",
                f"- Recursion limit: `{run_metadata.get('recursion_limit')}`",
                f"- Case timeout seconds: `{run_metadata.get('case_timeout_seconds')}`",
                f"- LLM model: `{run_metadata.get('llm_model')}`",
                f"- Embedding model: `{run_metadata.get('embedding_model')}`",
                "",
            ]
        )
        variants = run_metadata.get("variants") or {}
        if variants:
            lines.extend(["### Controlled Variables", ""])
            for key, value in sorted(variants.items()):
                lines.append(f"- `{key}`: `{value}`")
            lines.append("")

    lines.extend(
        [
        "## Summary",
        "",
        f"- Cases: {summary['case_count']}",
        f"- Retrieval hit rate: {format_percent(summary['custom_metrics']['retrieval_hit_rate'])}",
        f"- Agent retrieval hit rate: {format_percent(summary['custom_metrics']['agent_retrieval_hit_rate'])}",
        f"- RAG tool use rate: {format_percent(summary['custom_metrics']['rag_tool_use_rate'])}",
        f"- Empty retrieval rate: {format_percent(summary['custom_metrics']['empty_retrieval_rate'])}",
        f"- Avg retrieved contexts: {summary['custom_metrics']['avg_retrieved_context_count']:.2f}",
        f"- Avg latency: {summary['custom_metrics']['avg_latency_seconds']:.2f}s",
        f"- Timeouts: {summary['custom_metrics']['timeout_count']}",
        f"- Failures: {summary['custom_metrics']['failure_count']}",
        "",
        "## Ragas Metrics",
        "",
        "| Metric | Score |",
        "| --- | ---: |",
        ]
    )

    for key, value in summary["ragas_metrics"].items():
        lines.append(f"| {key} | {format_score(value)} |")

    lines.extend(
        [
            "",
            "## Ragas Metric Coverage",
            "",
            "| Metric | Valid | Missing | Valid Rate |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for key, coverage in summary.get("ragas_metric_coverage", {}).items():
        lines.append(
            f"| {key} | {coverage['valid_count']} | "
            f"{coverage['missing_count']} | {format_percent(coverage['valid_rate'])} |"
        )

    failed = [
        score
        for score in scores
        if score.error or not score.custom_metrics.get("agent_retrieval_hit")
    ][:20]
    lines.extend(["", "## First Cases To Inspect", ""])
    if not failed:
        lines.append("No obvious failed cases.")
    else:
        for score in failed:
            lines.extend(
                [
                    f"### {score.id}",
                    "",
                    f"- Error: `{score.error}`",
                    f"- RAG tool used: `{score.custom_metrics.get('rag_tool_used')}`",
                    f"- Agent retrieval hit: `{score.custom_metrics.get('agent_retrieval_hit')}`",
                    f"- Question: {score.question}",
                    f"- Reference: {score.reference}",
                    f"- Response: {score.response[:600]}",
                    "",
                ]
            )

    path.write_text("\n".join(lines), encoding="utf-8")


def write_reports(
    output_dir: Path,
    scores: list[CaseScore],
    run_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_scores(scores)
    if run_metadata:
        summary["run_metadata"] = run_metadata
        write_json(output_dir / "run_metadata.json", run_metadata)
    write_json(output_dir / "summary.json", summary)
    write_details(output_dir / "details.jsonl", scores)
    pd.DataFrame([flatten_score(score) for score in scores]).to_csv(
        output_dir / "summary.csv",
        index=False,
    )
    write_markdown_report(output_dir / "report.md", summary, scores, run_metadata)
    return summary
