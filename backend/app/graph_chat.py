"""
finance_tech.backend.app.graph_chat 的 Docstring
### 5. 实现最小 Chat Graph

需要实现：

- 创建 `graph_chat.py`
- 定义 ChatState
- 状态中至少包含 `messages`
- 用 `StateGraph` 创建一个单节点图
- 节点调用 LLM
- 编译时接入 checkpointer

核心结构：

```text
START -> chat -> END
```

建议文件：

```text
backend/app/graph_chat.py
```

验收标准：

- 后端可以调用 graph
- 输入 HumanMessage，输出 AIMessage
- 使用相同 thread_id 时，LangGraph 能保存消息状态
"""

import asyncio
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

try:
    from .checkpoint import get_checkpointer
    from .llm import get_llm
    from .vectorstore import similarity_search
except ImportError:
    from checkpoint import get_checkpointer
    from llm import get_llm
    from vectorstore import similarity_search


# 定义 ChatState
class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    rag_enabled: bool


def get_latest_user_message(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message.content
    return ""


def build_rag_system_message(query: str) -> SystemMessage:
    results = similarity_search(query, assistant_id="default", k=4)

    if not results:
        return SystemMessage(
            content=(
                "You are a helpful assistant.\n"
                "No relevant context was found in the uploaded files.\n"
                "Do not invent file-based facts. If the user asks about uploaded "
                "documents, say the uploaded files do not contain enough relevant "
                "information."
            )
        )

    context_parts = []
    for index, item in enumerate(results, start=1):
        metadata = item["metadata"]
        context_parts.append(
            f"[{index}] "
            f"filename={metadata.get('filename')}, "
            f"file_id={metadata.get('file_id')}, "
            f"chunk_index={metadata.get('chunk_index')}\n"
            f"{item['content']}"
        )

    context_text = "\n\n".join(context_parts)
    return SystemMessage(
        content=(
            "You are a helpful assistant.\n"
            "Use the retrieved context below to answer the user.\n"
            "If the answer is not in the context, say the uploaded files do not "
            "contain enough information.\n\n"
            f"Retrieved context:\n\n{context_text}"
        )
    )


# 定义 ChatNode
class ChatNode:
    def __init__(self):
        self.llm = get_llm()

    async def __call__(self, state: State, config: RunnableConfig) -> State:
        messages = state["messages"]

        if state.get("rag_enabled"):
            query = get_latest_user_message(messages)
            rag_message = build_rag_system_message(query)
            messages = [rag_message, *messages]

        # 调用 LLM 生成回复
        response = await self.llm.ainvoke(messages, config=config)
        print(f"LLM response: {response.content}")
        # 返回一个新状态：
        return {"messages": [response]}


builder = StateGraph(State)

builder.add_node("first_node", ChatNode())
builder.set_entry_point("first_node")
builder.set_finish_point("first_node")
graph = builder.compile(checkpointer=get_checkpointer())


# 测试调用
if __name__ == "__main__":
    config = {
        "configurable": {
            "thread_id": "graph_chat",
        }
    }
    initial_state: State = {
        "messages": [SystemMessage(content="You are a helpful assistant!")]
    }
    initial_state["messages"].append(HumanMessage(content="What is the capital of France?"))
    final_state = asyncio.run(graph.ainvoke(initial_state, config=config))

    print(f"Final state: {final_state}")
