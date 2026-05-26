from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from .checkpoint import get_checkpointer
from .llm import get_llm
from .tools import get_tool_callables


REACT_PROMPT = """
你是一个有能力调用外部工具的智能助手。

你可以根据用户问题决定是否调用工具：
- 如果问题需要查询、计算、检索或执行操作，请调用合适的工具。
- 如果问题可以直接回答，则直接回答。
- 不要编造工具结果。
- 工具返回后，请基于工具结果给出最终答案。
- 最终答案使用中文，结构清晰、简洁准确。
"""


class ReactAgent:
    def __init__(self):
        self.llm = get_llm()
        self.tools = get_tool_callables()
        self.graph = create_react_agent(
            self.llm,
            self.tools,
            checkpointer=get_checkpointer(),
            prompt=REACT_PROMPT,
        )


class ChatStrategy:
    def __init__(self):
        self.react_graph = ReactAgent().graph

    def select_graph_input(self, message: str):
        return self.react_graph, {
            "messages": [HumanMessage(content=message)],
        }
