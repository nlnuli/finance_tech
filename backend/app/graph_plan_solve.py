import json
import re
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent

from .checkpoint import get_checkpointer
from .llm import get_llm


MAX_PLAN_STEPS = 5
PLAN_EXECUTOR_REACT_PROMPT = """
你是计划执行器，也是一个可以调用外部工具的中文金融分析助手。

你的任务是：每次只执行用户计划中的当前步骤，并输出这一阶段的观察结果。

执行原则：
1. 如果当前步骤需要实时信息、外部资料、文档检索、计算或数据查询，请调用合适工具。
2. 如果当前步骤不需要工具，可以直接基于已有上下文给出观察结果。
3. 不要执行当前步骤之外的计划内容。
4. 不要编造工具没有返回的信息。
5. 工具结果不足时，要说明限制，并给出谨慎观察。
6. 输出应简洁，聚焦当前步骤的结论、依据和必要限制。
"""


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


def get_last_message_text(value: object) -> str:
    if isinstance(value, dict):
        messages = value.get("messages")
        if isinstance(messages, list) and messages:
            return get_text(messages[-1]).strip()

    return get_text(value).strip()


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
        self.agent = create_react_agent(
            get_llm(),
            tools,
            prompt=PLAN_EXECUTOR_REACT_PROMPT,
        )

    async def __call__(self, state: PlanSolveState, config: RunnableConfig) -> dict:
        step_index = state.get("current_step", 0)
        plan = state.get("plan", [])
        observations = state.get("observations", [])

        if step_index >= len(plan):
            return {}

        question = get_latest_user_message(state["messages"])
        step = plan[step_index]
        response = await self.agent.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content=(
                            f"用户问题：{question}\n"
                            f"完整计划：{json.dumps(plan, ensure_ascii=False)}\n"
                            f"已完成观察：{json.dumps(observations, ensure_ascii=False)}\n"
                            f"当前步骤：{step}\n\n"
                            "请只执行当前步骤，并返回该步骤的观察结果。"
                        )
                    )
                ]
            },
            config=config,
        )

        observation = (
            f"Step {step_index + 1}: {step}\n"
            f"Observation: {get_last_message_text(response)}"
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
