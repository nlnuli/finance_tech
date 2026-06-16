from __future__ import annotations

import re
from dataclasses import asdict
from math import isfinite
from typing import Any

from .models import AgentTrace, CaseScore, RagasCase, RetrievedContext
from .ragas_compat import patch_ragas_vertexai_import


def context_to_dict(context: RetrievedContext) -> dict[str, Any]:
    return asdict(context)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def contains_reference_context(
    retrieved_contexts: list[RetrievedContext],
    reference_contexts: list[str],
) -> bool:
    if not reference_contexts:
        return False

    retrieved_text = normalize_text(
        "\n".join(context.content for context in retrieved_contexts)
    )
    for reference_context in reference_contexts:
        normalized_reference = normalize_text(reference_context)
        if normalized_reference and normalized_reference[:240] in retrieved_text:
            return True
    return False


def source_file_hit(
    retrieved_contexts: list[RetrievedContext],
    source_files: list[str],
) -> bool:
    if not source_files or len(source_files) != 1:
        return False

    source_names = {str(source).split("/")[-1] for source in source_files}
    retrieved_names = {
        str(context.filename)
        for context in retrieved_contexts
        if context.filename is not None
    }
    return bool(source_names & retrieved_names)


def retrieval_hit(
    retrieved_contexts: list[RetrievedContext],
    case: RagasCase,
) -> bool:
    return contains_reference_context(
        retrieved_contexts=retrieved_contexts,
        reference_contexts=case.reference_contexts,
    ) or source_file_hit(
        retrieved_contexts=retrieved_contexts,
        source_files=case.source_files,
    )


def build_eval_rows(
    cases: list[RagasCase],
    traces: list[AgentTrace],
    direct_contexts_by_case: dict[str, list[RetrievedContext]],
) -> list[dict[str, Any]]:
    trace_by_id = {trace.case_id: trace for trace in traces}
    rows = []
    for case in cases:
        trace = trace_by_id[case.id]
        evaluation_contexts = (
            trace.retrieved_contexts
            or direct_contexts_by_case.get(case.id, [])
        )
        rows.append(
            {
                "user_input": case.question,
                "response": trace.final_answer,
                "retrieved_contexts": [
                    context.content for context in evaluation_contexts
                ],
                "reference": case.reference,
                "reference_contexts": case.reference_contexts,
            }
        )
    return rows


def get_ragas_metrics():
    patch_ragas_vertexai_import()
    from ragas.metrics import (
        AnswerRelevancy,
        Faithfulness,
        FactualCorrectness,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
    )

    return [
        Faithfulness(),
        AnswerRelevancy(),
        LLMContextPrecisionWithReference(),
        LLMContextRecall(),
        FactualCorrectness(),
    ]


def metric_name(metric) -> str:
    return getattr(metric, "name", metric.__class__.__name__)


def clean_metric_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number):
        return None
    return number


def run_ragas_evaluation(
    cases: list[RagasCase],
    traces: list[AgentTrace],
    direct_contexts_by_case: dict[str, list[RetrievedContext]],
) -> list[dict[str, float | None]]:
    if not cases:
        return []

    patch_ragas_vertexai_import()
    from ragas import EvaluationDataset, SingleTurnSample, evaluate

    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]
    backend_root = project_root / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from app.llm import get_llm
    from app.vectorstore import get_embeddings

    rows = build_eval_rows(
        cases=cases,
        traces=traces,
        direct_contexts_by_case=direct_contexts_by_case,
    )
    dataset = EvaluationDataset(
        samples=[SingleTurnSample(**row) for row in rows]
    )
    metrics = get_ragas_metrics()
    metric_names = [metric_name(metric) for metric in metrics]

    try:
        result = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=get_llm(),
            embeddings=get_embeddings(),
            raise_exceptions=False,
            show_progress=True,
        )
        frame = result.to_pandas()
    except Exception as exc:
        return [
            {"ragas_error": str(exc), **{name: None for name in metric_names}}
            for _ in cases
        ]

    scores: list[dict[str, float | None]] = []
    for _, row in frame.iterrows():
        score_row: dict[str, float | None] = {}
        for name in metric_names:
            score_row[name] = clean_metric_value(row.get(name))
        scores.append(score_row)
    return scores


def score_cases(
    cases: list[RagasCase],
    traces: list[AgentTrace],
    direct_contexts_by_case: dict[str, list[RetrievedContext]],
) -> list[CaseScore]:
    ragas_scores = run_ragas_evaluation(
        cases=cases,
        traces=traces,
        direct_contexts_by_case=direct_contexts_by_case,
    )
    trace_by_id = {trace.case_id: trace for trace in traces}
    scores: list[CaseScore] = []

    for index, case in enumerate(cases):
        trace = trace_by_id[case.id]
        direct_contexts = direct_contexts_by_case.get(case.id, [])
        evaluation_contexts = trace.retrieved_contexts or direct_contexts
        used_rag_tool = any(call.name == "rag_search" for call in trace.tool_calls)
        direct_retrieval_hit = retrieval_hit(direct_contexts, case)
        agent_retrieval_hit = retrieval_hit(evaluation_contexts, case)

        scores.append(
            CaseScore(
                id=case.id,
                question=case.question,
                reference=case.reference,
                response=trace.final_answer,
                source_files=case.source_files,
                retrieved_contexts=[
                    context_to_dict(context) for context in evaluation_contexts
                ],
                direct_retrieved_contexts=[
                    context_to_dict(context) for context in direct_contexts
                ],
                tool_calls=[asdict(call) for call in trace.tool_calls],
                ragas_metrics=ragas_scores[index] if index < len(ragas_scores) else {},
                custom_metrics={
                    "direct_retrieval_hit": direct_retrieval_hit,
                    "agent_retrieval_hit": agent_retrieval_hit,
                    "rag_tool_used": used_rag_tool,
                    "retrieved_context_count": len(evaluation_contexts),
                    "direct_retrieved_context_count": len(direct_contexts),
                    "empty_retrieval": len(direct_contexts) == 0,
                },
                latency_seconds=trace.latency_seconds,
                error=trace.error,
                timed_out=trace.timed_out,
            )
        )

    return scores
