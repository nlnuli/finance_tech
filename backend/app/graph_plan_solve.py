import json
import re
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from .checkpoint import get_checkpointer
from .llm import get_llm


MAX_PLAN_STEPS = 5


class PlanSolveState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    plan: list[str]
    current_step: int
    observations: list[str]


def get_latest_user_message(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)

    return ""


def get_text(value: object) -> str:
    content = getattr(value, "content", None)
    if content is not None:
        return get_text(content)

    if isinstance(value, str):
        return value

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    return str(value)


def extract_json_text(text: str) -> str:
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    return text


def parse_plan(text: str) -> list[str]:
    try:
        data = json.loads(extract_json_text(text))
        if isinstance(data, list):
            steps = [str(item).strip() for item in data if str(item).strip()]
            if steps:
                return steps[:MAX_PLAN_STEPS]
    except json.JSONDecodeError:
        pass

    lines = []
    for line in text.splitlines():
        line = line.strip()
        line = re.sub(r"^[-*\d.、\s]+", "", line)
        if line:
            lines.append(line)

    return lines[:MAX_PLAN_STEPS] or ["回答用户问题"]


def parse_tool_decision(text: str) -> dict:
    try:
        data = json.loads(extract_json_text(text))
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    return {
        "tool": "none",
        "input": {},
        "answer": text.strip(),
    }


def get_tool_arg_names(tool: object) -> list[str]:
    args = getattr(tool, "args", {})
    if isinstance(args, dict):
        return list(args.keys())
    return []


def normalize_tool_input(tool: object, tool_input: object) -> dict:
    if isinstance(tool_input, dict):
        return tool_input

    arg_names = get_tool_arg_names(tool)
    if len(arg_names) == 1:
        return {arg_names[0]: str(tool_input)}

    return {}


class PlannerNode:
    def __init__(self):
        self.llm = get_llm()

    async def __call__(self, state: PlanSolveState, config: RunnableConfig) -> dict:
        question = get_latest_user_message(state["messages"])
        response = await self.llm.ainvoke(
            [
                SystemMessage(
                    content=(
                        "你是任务规划器。请把用户问题拆成最多 5 个清晰步骤。\n"
                        "只返回 JSON 数组，不要返回 Markdown，不要解释。"
                    )
                ),
                HumanMessage(content=question),
            ],
            config=config,
        )
        return {
            "plan": parse_plan(get_text(response)),
            "current_step": 0,
            "observations": [],
        }


class ExecutorNode:
    def __init__(self, tools: list):
        self.llm = get_llm()
        self.tools = {tool.name: tool for tool in tools}
        self.tool_names = "、".join(self.tools.keys()) if self.tools else "无"

    async def __call__(self, state: PlanSolveState, config: RunnableConfig) -> dict:
        step_index = state.get("current_step", 0)
        plan = state.get("plan", [])
        observations = state.get("observations", [])

        if step_index >= len(plan):
            return {}

        question = get_latest_user_message(state["messages"])
        step = plan[step_index]
        response = await self.llm.ainvoke(
            [
                SystemMessage(
                    content=(
                        "你是计划执行器。你每次只执行一个步骤。\n"
                        f"可用工具：{self.tool_names}。\n"
                        "如果需要工具，只返回 JSON："
                        '{"tool":"工具名","input":{"参数名":"参数值"},"answer":""}\n'
                        "如果不需要工具，只返回 JSON："
                        '{"tool":"none","input":{},"answer":"你的观察结果"}\n'
                        "不要返回 Markdown。"
                    )
                ),
                HumanMessage(
                    content=(
                        f"用户问题：{question}\n"
                        f"完整计划：{json.dumps(plan, ensure_ascii=False)}\n"
                        f"已完成观察：{json.dumps(observations, ensure_ascii=False)}\n"
                        f"当前步骤：{step}"
                    )
                ),
            ],
            config=config,
        )

        decision = parse_tool_decision(get_text(response))
        tool_name = str(decision.get("tool", "none"))

        if tool_name not in self.tools:
            observation = (
                f"Step {step_index + 1}: {step}\n"
                f"Observation: {decision.get('answer', '').strip()}"
            )
        else:
            tool = self.tools[tool_name]
            tool_input = normalize_tool_input(tool, decision.get("input") or {})

            try:
                tool_result = await tool.ainvoke(tool_input, config=config)
                result_text = get_text(tool_result)
            except Exception as exc:
                result_text = f"{tool_name} error: {exc}"

            observation = (
                f"Step {step_index + 1}: {step}\n"
                f"Tool: {tool_name}\n"
                f"Input: {json.dumps(tool_input, ensure_ascii=False)}\n"
                f"Result: {result_text}"
            )

        return {
            "current_step": step_index + 1,
            "observations": observations + [observation],
        }


class SolverNode:
    def __init__(self):
        self.llm = get_llm()

    async def __call__(self, state: PlanSolveState, config: RunnableConfig) -> dict:
        question = get_latest_user_message(state["messages"])
        response = await self.llm.ainvoke(
            [
                SystemMessage(
                    content=(
                        "你是最终回答生成器。请根据计划和每一步观察结果回答用户问题。\n"
                        "不要编造观察结果中没有的信息。最终答案使用中文，结构清晰、简洁准确。"
                    )
                ),
                HumanMessage(
                    content=(
                        f"用户问题：{question}\n"
                        f"计划：{json.dumps(state.get('plan', []), ensure_ascii=False)}\n"
                        f"观察结果：{json.dumps(state.get('observations', []), ensure_ascii=False)}"
                    )
                ),
            ],
            config=config,
        )
        return {"messages": [AIMessage(content=get_text(response))]}


def should_continue(state: PlanSolveState) -> str:
    if state.get("current_step", 0) < len(state.get("plan", [])):
        return "executor"
    return "solver"


def create_plan_solve_graph(tools: list):
    builder = StateGraph(PlanSolveState)
    builder.add_node("planner", PlannerNode())
    builder.add_node("executor", ExecutorNode(tools))
    builder.add_node("solver", SolverNode())

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "executor")
    builder.add_conditional_edges(
        "executor",
        should_continue,
        {
            "executor": "executor",
            "solver": "solver",
        },
    )
    builder.add_edge("solver", END)
    return builder.compile(checkpointer=get_checkpointer())
