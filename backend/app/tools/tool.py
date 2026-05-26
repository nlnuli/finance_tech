import ast
import operator
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.tools import StructuredTool
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from ..vectorstore import similarity_search

ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

ALLOWED_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class CalculatorInput(BaseModel):
    expression: str = Field(description="A safe math expression, for example: 1 + 2 * (3 + 4)")


class CurrentTimeInput(BaseModel):
    timezone: str = Field(default="Asia/Shanghai", description="IANA timezone name")


def format_search_results(results: list[dict]) -> str:
    if not results:
        return "No relevant chunks found."

    parts = []
    for index, item in enumerate(results, start=1):
        metadata = item["metadata"]
        parts.append(
            f"[{index}] "
            f"filename={metadata.get('filename')}, "
            f"file_id={metadata.get('file_id')}, "
            f"chunk_index={metadata.get('chunk_index')}\n"
            f"{item['content']}"
        )

    return "\n\n".join(parts)


@tool
def rag_search(query: str) -> str:
    """Search uploaded financial documents and return relevant chunks with source metadata."""
    results = similarity_search(
        query=query,
        assistant_id="default",
        k=4,
    )
    return format_search_results(results)


def evaluate_math_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return evaluate_math_node(node.body)

    if isinstance(node, ast.Constant):
        if type(node.value) in (int, float):
            return node.value
        raise ValueError("only numbers are supported")

    if isinstance(node, ast.BinOp):
        operator_func = ALLOWED_OPERATORS.get(type(node.op))
        if not operator_func:
            raise ValueError("unsupported operator")

        left = evaluate_math_node(node.left)
        right = evaluate_math_node(node.right)

        if isinstance(node.op, ast.Pow) and abs(right) > 12:
            raise ValueError("power is too large")

        return operator_func(left, right)

    if isinstance(node, ast.UnaryOp):
        operator_func = ALLOWED_UNARY_OPERATORS.get(type(node.op))
        if not operator_func:
            raise ValueError("unsupported unary operator")
        return operator_func(evaluate_math_node(node.operand))

    raise ValueError("unsupported expression")


def run_calculator(expression: str) -> str:
    try:
        tree = ast.parse(expression, mode="eval")
        result = evaluate_math_node(tree)
        return f"result: {result}"
    except Exception as exc:
        return f"calculator error: {exc}"


def run_current_time(timezone: str = "Asia/Shanghai") -> str:
    try:
        current = datetime.now(ZoneInfo(timezone))
        return f"current time in {timezone}: {current:%Y-%m-%d %H:%M:%S}"
    except ZoneInfoNotFoundError:
        return f"current_time error: invalid timezone {timezone}"


calculator = StructuredTool.from_function(
    func=run_calculator,
    name="calculator",
    description="Safely evaluate a basic math expression.",
    args_schema=CalculatorInput,
)

current_time = StructuredTool.from_function(
    func=run_current_time,
    name="current_time",
    description="Return the current time for an IANA timezone.",
    args_schema=CurrentTimeInput,
)


def get_all_tools() -> list:
    return [
        rag_search,
        calculator,
        current_time,
    ]
