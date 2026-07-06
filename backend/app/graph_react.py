from langgraph.prebuilt import create_react_agent

from .agent import REACT_PROMPT
from .checkpoint import get_checkpointer
from .llm import get_llm


def create_react_graph(tools: list):
    return create_react_agent(
        get_llm(),
        tools,
        checkpointer=get_checkpointer(),
        prompt=REACT_PROMPT,
    )
