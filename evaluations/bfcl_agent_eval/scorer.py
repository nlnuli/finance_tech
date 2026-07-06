from __future__ import annotations

import math
from collections import Counter
from typing import Any

from .models import AgentTrace, BFCLCase, CaseScore, ExpectedCall, ToolCallRecord


def normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_value(value[key]) for key in sorted(value)}
    return value


def values_equal(actual: Any, expected: Any) -> bool:
    actual = normalize_value(actual)
    expected = normalize_value(expected)

    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=1e-6, abs_tol=1e-6)

    return actual == expected


def value_matches_any(actual: Any, accepted_values: list[Any]) -> bool:
    return any(values_equal(actual, expected) for expected in accepted_values)


def missing_value_is_accepted(accepted_values: list[Any]) -> bool:
    return any(values_equal("", expected) for expected in accepted_values)


def call_to_dict(call: ExpectedCall | ToolCallRecord) -> dict[str, Any]:
    if isinstance(call, ExpectedCall):
        return {"name": call.name, "arguments": call.arguments}
    return {
        "name": call.name,
        "arguments": call.arguments,
        "output": call.output,
        "error": call.error,
    }


def tool_name_accuracy(
    expected_calls: list[ExpectedCall],
    actual_calls: list[ToolCallRecord],
) -> float:
    if not expected_calls and not actual_calls:
        return 1.0
    if not expected_calls:
        return 0.0

    expected_names = Counter(call.name for call in expected_calls)
    actual_names = Counter(call.name for call in actual_calls)
    correct = sum(min(count, actual_names[name]) for name, count in expected_names.items())
    return correct / len(expected_calls)


def select_best_actual_call(
    expected_call: ExpectedCall,
    actual_calls: list[ToolCallRecord],
    used_indexes: set[int],
) -> tuple[int | None, ToolCallRecord | None]:
    best_index = None
    best_call = None
    best_score = -1

    for index, actual_call in enumerate(actual_calls):
        if index in used_indexes or actual_call.name != expected_call.name:
            continue

        score = 0
        for key, accepted_values in expected_call.arguments.items():
            if key in actual_call.arguments and value_matches_any(
                actual_call.arguments[key],
                accepted_values,
            ):
                score += 1

        if score > best_score:
            best_index = index
            best_call = actual_call
            best_score = score

    return best_index, best_call


def score_arguments(
    expected_calls: list[ExpectedCall],
    actual_calls: list[ToolCallRecord],
) -> tuple[float, float, bool]:
    total_params = 0
    key_hits = 0
    value_hits = 0
    all_expected_matched = True
    used_indexes: set[int] = set()

    for expected_call in expected_calls:
        index, actual_call = select_best_actual_call(expected_call, actual_calls, used_indexes)
        if index is not None:
            used_indexes.add(index)

        if actual_call is None:
            all_expected_matched = False

        for key, accepted_values in expected_call.arguments.items():
            total_params += 1
            if actual_call is None:
                all_expected_matched = False
                continue

            has_key = key in actual_call.arguments
            if has_key or missing_value_is_accepted(accepted_values):
                key_hits += 1

            if has_key:
                if value_matches_any(actual_call.arguments[key], accepted_values):
                    value_hits += 1
                else:
                    all_expected_matched = False
            elif missing_value_is_accepted(accepted_values):
                value_hits += 1
            else:
                all_expected_matched = False

    if total_params == 0:
        return 1.0, 1.0, all_expected_matched and not actual_calls

    return key_hits / total_params, value_hits / total_params, all_expected_matched


def score_case(case: BFCLCase, trace: AgentTrace) -> CaseScore:
    expected_calls = case.expected_calls
    actual_calls = trace.tool_calls

    if not expected_calls:
        no_call_correct = len(actual_calls) == 0
        return CaseScore(
            id=case.id,
            category=case.category,
            exact_match=no_call_correct and trace.error is None,
            call_count_correct=no_call_correct,
            tool_name_accuracy=1.0 if no_call_correct else 0.0,
            argument_key_accuracy=1.0 if no_call_correct else 0.0,
            argument_value_accuracy=1.0 if no_call_correct else 0.0,
            no_call_correct=no_call_correct,
            expected_calls=[],
            actual_calls=[call_to_dict(call) for call in actual_calls],
            final_answer=trace.final_answer,
            latency_seconds=trace.latency_seconds,
            error=trace.error,
        )

    arg_key_accuracy, arg_value_accuracy, args_exact = score_arguments(
        expected_calls,
        actual_calls,
    )
    call_count_correct = len(expected_calls) == len(actual_calls)
    names_correct = Counter(call.name for call in expected_calls) == Counter(
        call.name for call in actual_calls
    )
    exact_match = (
        call_count_correct
        and names_correct
        and args_exact
        and trace.error is None
    )

    return CaseScore(
        id=case.id,
        category=case.category,
        exact_match=exact_match,
        call_count_correct=call_count_correct,
        tool_name_accuracy=tool_name_accuracy(expected_calls, actual_calls),
        argument_key_accuracy=arg_key_accuracy,
        argument_value_accuracy=arg_value_accuracy,
        no_call_correct=None,
        expected_calls=[call_to_dict(call) for call in expected_calls],
        actual_calls=[call_to_dict(call) for call in actual_calls],
        final_answer=trace.final_answer,
        latency_seconds=trace.latency_seconds,
        error=trace.error,
    )
