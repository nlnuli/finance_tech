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

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END

from checkpoint import get_checkpointer
from llm import get_llm

from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages

# 定义 ChatState
class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

# 定义 ChatNode
class ChatNode():
    def __init__(self):
        self.llm = get_llm()
    def __call__(self, state: State) -> State:
        # 调用 LLM 生成回复
        response = self.llm.invoke(state["messages"])
        print(f"LLM response: {response.content}")
        # 返回一个新状态：
        return {
            "messages": [response]
        }
    
       

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
        "messages": [SystemMessage(content="Your are a helpful assistant!")]
    }
    initial_state["messages"].append(HumanMessage(content="What is the capital of France?"))
    final_state = graph.invoke(initial_state, config=config)

    print(f"Final state: {final_state}")