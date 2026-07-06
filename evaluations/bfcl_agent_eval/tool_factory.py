from __future__ import annotations

import re
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import Field, create_model

from .models import ToolCallRecord


TOOL_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_-]")
PARAM_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_]")


class ToolCallRecorder:
    def __init__(self):
        self.calls: list[ToolCallRecord] = []
        self.safe_to_original: dict[str, str] = {}
        self.safe_param_to_original: dict[str, dict[str, str]] = {}

    def original_name(self, safe_name: str) -> str:
        return self.safe_to_original.get(safe_name, safe_name)

    def record(self, safe_name: str, arguments: dict[str, Any]) -> str:
        original_name = self.original_name(safe_name)
        original_arguments = {
            self.safe_param_to_original.get(safe_name, {}).get(key, key): value
            for key, value in arguments.items()
        }
        output = (
            f"stub result for {original_name}: "
            f"received arguments {original_arguments}"
        )
        self.calls.append(
            ToolCallRecord(
                name=original_name,
                arguments=original_arguments,
                output=output,
            )
        )
        return output


def sanitize_tool_name(name: str, used_names: set[str]) -> str:
    safe_name = TOOL_NAME_PATTERN.sub("_", name)
    if not safe_name:
        safe_name = "tool"

    candidate = safe_name
    index = 2
    while candidate in used_names:
        candidate = f"{safe_name}_{index}"
        index += 1

    used_names.add(candidate)
    return candidate


def sanitize_param_name(name: str, used_names: set[str]) -> str:
    safe_name = PARAM_NAME_PATTERN.sub("_", name).lstrip("_")
    if not safe_name:
        safe_name = "param"

    candidate = safe_name
    index = 2
    while candidate in used_names:
        candidate = f"{safe_name}_{index}"
        index += 1

    used_names.add(candidate)
    return candidate


def python_type_from_json_schema(schema: dict[str, Any]):
    schema_type = schema.get("type")
    if schema_type == "integer":
        return int
    if schema_type in {"number", "float"}:
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        return list
    if schema_type in {"object", "dict"}:
        return dict
    if schema_type == "string":
        return str
    return Any


def build_args_schema(
    function_doc: dict[str, Any],
    safe_name: str,
) -> tuple[type, dict[str, str]]:
    parameters = function_doc.get("parameters", {})
    properties = parameters.get("properties", {})
    required = set(parameters.get("required", []))
    fields = {}
    used_param_names: set[str] = set()
    safe_param_to_original: dict[str, str] = {}

    for param_name, param_schema in properties.items():
        safe_param_name = sanitize_param_name(param_name, used_param_names)
        safe_param_to_original[safe_param_name] = param_name
        annotation = python_type_from_json_schema(param_schema)
        default = ... if param_name in required else None
        description = param_schema.get("description", "")
        if safe_param_name != param_name:
            description = (
                f"{description} Original BFCL parameter name: {param_name}."
            ).strip()
        fields[safe_param_name] = (
            annotation,
            Field(
                default,
                description=description,
            ),
        )

    return create_model(f"{safe_name}_Arguments", **fields), safe_param_to_original


def make_stub_tools(
    functions: list[dict[str, Any]],
) -> tuple[list[StructuredTool], ToolCallRecorder]:
    recorder = ToolCallRecorder()
    tools: list[StructuredTool] = []
    used_names: set[str] = set()

    for function_doc in functions:
        original_name = function_doc["name"]
        safe_name = sanitize_tool_name(original_name, used_names)
        recorder.safe_to_original[safe_name] = original_name
        args_schema, safe_param_to_original = build_args_schema(function_doc, safe_name)
        recorder.safe_param_to_original[safe_name] = safe_param_to_original

        async def stub_tool(_safe_name=safe_name, **kwargs):
            return recorder.record(_safe_name, kwargs)

        stub_tool.__name__ = f"stub_{safe_name}"
        tools.append(
            StructuredTool.from_function(
                coroutine=stub_tool,
                name=safe_name,
                description=function_doc.get("description", ""),
                args_schema=args_schema,
            )
        )

    return tools, recorder
