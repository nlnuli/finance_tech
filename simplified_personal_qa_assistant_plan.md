# 简化版个人问答助手实现文档

本文档用于后续在一个新的 workspace 中，从零实现一个简化版个人问答助手。目标不是复刻 OpenGPTs 的全部能力，而是借鉴它的核心设计思想，优先完成以下功能：

1. Chat 对话
2. 用户上传文件后支持 RAG 问答
3. 支持 Tool 调用，并且 Tool 易于配置
4. 支持 ReAct Agent 和 Plan-Solve Agent 两种模式
5. 支持 LangGraph checkpoint 存储与恢复
6. 前后端支持流式响应

## 一、项目目标

最终系统应该支持：

- 用户创建或使用一个默认助手
- 用户开启一个对话线程
- 用户输入问题并看到流式回复
- 用户上传文件后，可以基于文件内容问答
- 用户可以开启或关闭某些工具
- 用户可以选择普通 Chat、ReAct Agent、Plan-Solve Agent
- 后端保存历史消息
- 后端通过 LangGraph checkpoint 保存和恢复 agent 执行状态
- 前端可以恢复历史对话

第一版不追求：

- 多用户复杂权限
- OAuth / OIDC / JWT 认证
- 多模型供应商完整适配
- 公开分享 assistant
- LangSmith feedback
- 大量第三方工具
- 多人协作编辑 thread
- 复杂人工审批工作流

## 二、推荐技术栈

后端：

```text
Python
FastAPI
LangChain
LangGraph
SQLAlchemy / SQLModel
SQLite 或 Postgres
Chroma / FAISS / pgvector
Server-Sent Events
```

前端：

```text
React
TypeScript
Vite
fetch-event-source 或原生 EventSource/fetch stream
```

第一版建议：

```text
数据库：SQLite
向量库：Chroma
模型：OpenAI 或 Ollama 二选一
Agent 编排：LangGraph
Checkpoint：第一版使用 SQLite/Postgres checkpointer 二选一
流式协议：SSE
```

如果你希望更接近生产环境，建议直接使用 Postgres + pgvector + LangGraph Postgres checkpoint。

## 三、核心架构

推荐目录结构：

```text
personal-qa-assistant/
  backend/
    app/
      main.py
      config.py
      db.py
      models.py
      schemas.py
      storage.py
      llm.py
      chat.py
      rag.py
      tools.py
      agent.py
      graph_chat.py
      graph_react.py
      graph_plan_solve.py
      checkpoint.py
      stream.py
      uploads.py
    requirements.txt

  frontend/
    src/
      App.tsx
      api.ts
      hooks/
        useChatStream.ts
      components/
        ChatPage.tsx
        MessageList.tsx
        MessageInput.tsx
        FileUpload.tsx
        ToolConfig.tsx
```

模块职责：

```text
main.py
FastAPI 入口，注册 API 路由。

config.py
读取环境变量，例如 OPENAI_API_KEY、DATABASE_URL。

db.py
数据库连接和 session 管理。

models.py
数据库 ORM 模型。

schemas.py
API 请求体和响应体模型。

storage.py
封装 assistant、thread、message、file 的读写。

llm.py
封装模型初始化和调用。

chat.py
普通聊天逻辑。

rag.py
文件解析、切块、向量化、检索、RAG prompt。

tools.py
Tool 注册表、Tool 配置 schema、Tool 执行函数。

agent.py
统一选择普通 Chat、ReAct、Plan-Solve 等 agent 模式。

graph_chat.py
使用 LangGraph 实现普通 Chat 图。

graph_react.py
使用 LangGraph 实现 ReAct 工具调用图。

graph_plan_solve.py
使用 LangGraph 实现 Plan-Solve 图。

checkpoint.py
初始化 LangGraph checkpointer，负责 thread 状态持久化。

stream.py
把后端事件转换成 SSE。

uploads.py
处理文件上传、保存和入库。
```

## 四、数据模型设计

最小可用表：

```sql
assistant
- id
- name
- system_prompt
- model
- mode                 -- chat / react / plan_solve
- rag_enabled
- tools_config JSON
- created_at
- updated_at

thread
- id
- assistant_id
- title
- created_at
- updated_at

message
- id
- thread_id
- role
- content
- tool_name
- tool_call_id
- created_at

file
- id
- assistant_id
- filename
- content_type
- created_at

document_chunk
- id
- assistant_id
- file_id
- content
- metadata JSON
- vector_id

checkpoint
- 由 LangGraph checkpointer 管理
- 用 thread_id / assistant_id 等 configurable 字段定位
```

第一版可以简化：

- 不做 `document_chunk` 表，让向量库自己保存 chunk metadata
- 不做 `tool_name` 和 `tool_call_id`，直到 Tool 功能开始实现
- checkpoint 表尽量使用 LangGraph 官方 checkpointer 自动创建

建议第一版保留 `assistant`，因为 agent mode、RAG 和 Tool 配置都适合挂在 assistant 上。

## 五、统一请求链路

一次用户提问的完整链路：

```text
前端 MessageInput
-> POST /api/chat/stream
-> 后端读取 assistant/thread/history
-> 保存 user message
-> agent.py 根据 assistant.mode 选择 LangGraph 图
-> LangGraph 根据 config.thread_id 从 checkpoint 恢复状态
-> 图节点调用 LLM、RAG、tools 或 planner/solver
-> 保存 assistant message
-> SSE 返回 token/message/tool 事件
-> LangGraph checkpointer 保存最新状态
-> 前端合并并展示消息
```

推荐 API：

```http
POST /api/chat/stream
```

请求体：

```json
{
  "assistant_id": "default",
  "thread_id": "thread_123",
  "message": "请总结我上传的文件",
  "mode": "react"
}
```

响应：

```text
Content-Type: text/event-stream
```

SSE 事件：

```text
event: metadata
data: {"run_id":"run_xxx"}

event: token
data: {"content":"你好"}

event: tool_start
data: {"name":"calculator","args":{"expression":"1+1"}}

event: tool_result
data: {"name":"calculator","content":"2"}

event: plan
data: {"steps":["检索文件","总结内容","给出结论"]}

event: checkpoint
data: {"thread_id":"thread_123","next":["agent"]}

event: message
data: {"role":"assistant","content":"完整回答"}

event: end
data: {}
```

## 六、阶段一：普通 Chat + 流式响应

目标：

- 后端能收到用户消息
- 使用 LangChain 调用 LLM
- 使用 LangGraph 构建最小 Chat 图
- 使用 checkpointer 按 thread_id 保存状态
- 流式返回 token
- 前端实时显示

后端先实现：

```text
POST /api/chat/stream
GET /api/threads
GET /api/threads/{thread_id}/messages
POST /api/threads
```

核心函数：

```python
from typing import Annotated

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages


class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_chat_graph(llm, checkpointer, system_prompt: str):
    async def call_model(state: ChatState):
        messages = [SystemMessage(content=system_prompt)] + state["messages"]
        response = await llm.ainvoke(messages)
        return {"messages": [response]}

    graph = StateGraph(ChatState)
    graph.add_node("chat", call_model)
    graph.set_entry_point("chat")
    graph.set_finish_point("chat")
    return graph.compile(checkpointer=checkpointer)
```

运行时 config：

```python
config = {
    "configurable": {
        "thread_id": thread_id,
        "assistant_id": assistant_id,
    }
}
```

说明：

- `messages` 由 LangGraph 状态管理
- 每次调用图时传入新的 `HumanMessage`
- checkpointer 根据 `thread_id` 保存状态
- 前端仍然通过 SSE 接收流式事件

前端先实现：

- 消息列表
- 输入框
- 发送按钮
- SSE 接收 token
- 把 token 拼到当前 assistant 消息上

验收标准：

- 输入一句话，前端能看到逐步输出
- 刷新页面后能恢复历史消息

## 七、阶段二：保存 Thread 和 Message

目标：

- 多轮对话可持续
- 每个 thread 有独立历史
- 前端可切换 thread
- 数据库保存业务消息
- LangGraph checkpoint 保存图执行状态

后端接口：

```http
POST /api/threads
GET /api/threads
GET /api/threads/{thread_id}
GET /api/threads/{thread_id}/messages
DELETE /api/threads/{thread_id}
```

Message 格式：

```json
{
  "id": "msg_xxx",
  "thread_id": "thread_xxx",
  "role": "user",
  "content": "你好",
  "created_at": "..."
}
```

注意：

- 用户消息在调用 LLM 前保存
- assistant 消息在流式完成后保存
- 如果流式中断，可以选择不保存 assistant 消息，或保存 partial 状态
- 数据库 message 表用于展示历史
- LangGraph checkpoint 用于恢复 agent 内部状态
- 两者可以同时存在，不要混为一谈

业务消息与 checkpoint 的区别：

```text
message 表
给前端展示、搜索、导出使用。

checkpoint
给 LangGraph 恢复执行状态使用，可能包含 messages、next、tasks、interrupts 等内部信息。
```

## 八、阶段三：Checkpoint 存储

目标：

- 使用 LangGraph 官方 checkpointer
- 按 thread_id 保存和恢复状态
- 支持 Chat/ReAct/Plan-Solve 共享 checkpoint 机制

第一版选择：

```text
本地开发：SqliteSaver 或 MemorySaver
更接近生产：PostgresSaver / AsyncPostgresSaver
```

推荐生产方案：

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool


async def create_checkpointer(database_url: str):
    pool = AsyncConnectionPool(
        conninfo=database_url,
        kwargs={"autocommit": True, "prepare_threshold": 0},
        open=False,
    )
    await pool.open()
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()
    return checkpointer
```

调用图时必须传 config：

```python
config = {
    "configurable": {
        "thread_id": thread_id,
        "assistant_id": assistant_id,
    }
}
```

读取状态：

```python
snapshot = await graph.aget_state(config)
values = snapshot.values
next_nodes = snapshot.next
```

接口建议：

```http
GET /api/threads/{thread_id}/state
GET /api/threads/{thread_id}/history
POST /api/threads/{thread_id}/resume
```

验收标准：

- 同一个 thread_id 多次调用可以看到历史状态
- 服务重启后 checkpoint 仍可恢复
- 前端可以根据 `next` 判断是否需要“继续执行”

## 九、阶段四：文件上传与入库

目标：

- 用户上传 PDF/TXT/DOCX
- 后端解析文本
- 切块
- 生成 embedding
- 存入向量库

接口：

```http
POST /api/files/upload
```

请求：

```text
multipart/form-data
- assistant_id
- file
```

处理流程：

```text
UploadFile
-> 保存 file 记录
-> 根据 mimetype 解析文本
-> RecursiveCharacterTextSplitter 切块
-> embedding
-> vectorstore.add_documents
-> metadata 写入 assistant_id、file_id、filename
```

推荐 chunk 参数：

```python
chunk_size = 1000
chunk_overlap = 200
```

第一版支持文件类型：

```text
.txt
.md
.pdf
.docx
```

先不要支持太多格式，解析失败要给出明确错误。

## 十、阶段五：RAG 问答

目标：

- 如果 assistant 下有上传文件，用户提问时可以检索相关 chunks
- 模型基于 context 回答
- 回答中尽量避免编造

推荐流程一：Chat/RAG 直接模式

```text
用户问题
-> 向量检索 top_k chunks
-> 构造 RAG system prompt
-> 附加历史消息
-> 调用 LLM 流式回答
```

RAG prompt：

```text
你是一个个人问答助手。
请优先使用下面的资料回答用户问题。
如果资料中没有答案，请明确说明“上传资料中没有找到相关信息”。
不要编造资料中不存在的内容。

资料：
{context}
```

核心函数：

```python
async def build_rag_messages(assistant_id: str, question: str, history: list):
    docs = vectorstore.similarity_search(
        question,
        k=5,
        filter={"assistant_id": assistant_id},
    )
    context = "\n\n".join(doc.page_content for doc in docs)

    return [
        {"role": "system", "content": rag_prompt.format(context=context)},
        *history,
        {"role": "user", "content": question},
    ]
```

是否自动启用 RAG：

第一版建议简单处理：

```text
只要 assistant 有上传文件，就自动检索。
```

后续再加开关：

```json
{
  "rag_enabled": true
}
```

推荐流程二：RAG 作为 Tool

如果当前 assistant 使用 ReAct 或 Plan-Solve，可以把 RAG 检索注册成工具：

```text
rag_search(query: str) -> list[DocumentChunk]
```

这样模型可以自行决定什么时候检索文件。

建议：

- `mode=chat` 时，RAG 可以自动注入 context
- `mode=react` 时，RAG 更适合作为工具
- `mode=plan_solve` 时，planner 可以把“检索资料”列为计划步骤

## 十一、阶段六：Tool 注册表

目标：

- Tool 易于新增
- Tool 可配置启用/禁用
- Agent 可以根据配置加载 tools

工具配置结构：

```json
{
  "tools": [
    {
      "type": "calculator",
      "enabled": true,
      "config": {}
    },
    {
      "type": "web_search",
      "enabled": false,
      "config": {
        "max_results": 3
      }
    }
  ]
}
```

后端 Tool 定义建议直接兼容 LangChain：

```python
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class CalculatorInput(BaseModel):
    expression: str = Field(description="Math expression to evaluate")


async def calculator(expression: str) -> str:
    ...


calculator_tool = StructuredTool.from_function(
    coroutine=calculator,
    name="calculator",
    description="Evaluate a math expression.",
    args_schema=CalculatorInput,
)
```

注册表：

```python
TOOL_REGISTRY = {
    "calculator": calculator_tool,
    "web_search": web_search_tool,
    "rag_search": rag_search_tool,
}
```

加载启用工具：

```python
def load_enabled_tools(tools_config: list[dict]) -> list:
    tools = []
    for item in tools_config:
        if not item.get("enabled", False):
            continue
        tool_type = item["type"]
        tools.append(TOOL_REGISTRY[tool_type])
    return tools
```

第一版建议实现三个工具：

```text
calculator
执行简单数学表达式。

rag_search
显式搜索用户上传文件。

current_time
返回当前时间。
```

web_search 可以后面再做，因为它涉及第三方 API 和联网结果质量。

## 十二、阶段七：ReAct Agent

目标：

- 使用 LangGraph 实现 ReAct 模式
- LLM 可以调用工具
- 工具结果写回图状态
- 支持 checkpoint 恢复
- 支持 SSE 输出 token/tool 事件

ReAct 思路：

```text
用户问题
-> agent 节点调用 LLM
-> 如果 LLM 返回 tool_calls，进入 tools 节点
-> tools 节点执行工具
-> 工具结果加入 messages
-> 回到 agent 节点
-> 直到 LLM 不再调用工具
-> END
```

可以优先使用 LangGraph 预构建能力：

```python
from langgraph.prebuilt import create_react_agent


def build_react_graph(llm, tools, checkpointer, system_prompt: str):
    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=system_prompt,
        checkpointer=checkpointer,
    )
```

如果需要更容易学习，也可以手写图：

```python
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode


class ReActState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_react_graph(llm, tools, checkpointer):
    llm_with_tools = llm.bind_tools(tools)
    tool_node = ToolNode(tools)

    async def agent_node(state: ReActState):
        response = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: ReActState):
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        return END

    graph = StateGraph(ReActState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue)
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=checkpointer)
```

SSE 映射：

```text
on_chat_model_stream -> token
tools 节点开始 -> tool_start
tools 节点输出 -> tool_result
graph end -> message/end
```

验收标准：

- assistant 开启 calculator 后，用户问 “12 * 8 等于多少” 会调用工具
- tool_start/tool_result 会显示在前端
- thread 刷新后状态可以从 checkpoint 恢复

## 十三、阶段八：Plan-Solve Agent

目标：

- 支持先规划，再执行，再总结
- 适合多步骤问题、复杂 RAG、多个工具组合
- 仍然使用 LangGraph 和 checkpoint

Plan-Solve 基本流程：

```text
planner 节点
生成步骤计划

executor 节点
逐步执行计划，可以调用 RAG/tool

solver 节点
根据执行结果生成最终回答
```

状态设计：

```python
from typing import Annotated, TypedDict
import operator

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class PlanSolveState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    plan: list[str]
    current_step: int
    observations: Annotated[list[str], operator.add]
```

图结构：

```text
planner -> executor -> should_continue
                       -> executor
                       -> solver -> END
```

伪代码：

```python
def build_plan_solve_graph(llm, tools, checkpointer):
    async def planner(state):
        plan = await planner_chain.ainvoke({"messages": state["messages"]})
        return {"plan": plan, "current_step": 0}

    async def executor(state):
        step = state["plan"][state["current_step"]]
        result = await execute_step_with_tools(step, state, tools)
        return {
            "observations": [result],
            "current_step": state["current_step"] + 1,
        }

    def should_continue(state):
        if state["current_step"] < len(state["plan"]):
            return "executor"
        return "solver"

    async def solver(state):
        answer = await solver_chain.ainvoke(state)
        return {"messages": [answer]}
```

第一版 Plan-Solve 可以简化：

- planner 只输出 JSON list[str]
- executor 每一步直接让 LLM 决定是否调用工具
- solver 汇总 `plan + observations + 原问题`
- 最大步骤数限制为 5

Plan prompt：

```text
你是任务规划器。
请把用户问题拆成最多 5 个可执行步骤。
如果需要查上传文件，请包含“检索相关文件内容”。
如果需要计算，请包含“调用计算工具”。
只返回 JSON 字符串数组。
```

Solve prompt：

```text
你是回答生成器。
请根据用户问题、计划步骤和每一步观察结果，给出最终答案。
不要编造观察结果中没有的信息。
```

SSE 新增事件：

```text
plan
返回计划步骤。

step_start
当前执行哪一步。

step_result
当前步骤结果。
```

验收标准：

- 复杂问题会先产生 plan
- 前端能看到 plan/step 过程
- 每一步结果进入 checkpoint
- 最终回答能汇总多个步骤

## 十四、阶段九：前端 Agent 模式配置

目标：

- 用户可以选择 assistant mode
- 支持 chat / react / plan_solve
- 不同模式显示不同配置项

assistant 配置：

```json
{
  "mode": "react",
  "model": "gpt-4o-mini",
  "system_prompt": "你是一个个人问答助手",
  "rag_enabled": true,
  "tools": [
    {"type": "calculator", "enabled": true, "config": {}},
    {"type": "rag_search", "enabled": true, "config": {}}
  ]
}
```

前端 UI：

```text
Agent Mode:
( ) Chat
(x) ReAct
( ) Plan-Solve

RAG:
[x] Use uploaded files

Tools:
[x] Calculator
[x] RAG Search
[ ] Web Search
```

模式解释：

```text
Chat
最简单，适合普通对话和自动 RAG。

ReAct
适合需要模型自主调用工具的任务。

Plan-Solve
适合复杂、多步骤、需要先规划再执行的问题。
```

## 十五、阶段十：Tool Calling Loop

目标：

- 模型可以决定是否调用工具
- 后端执行工具
- 工具结果回传给模型
- 模型生成最终回答

如果使用 LangGraph ReAct，这一阶段主要用于理解和定制工具循环。
生产实现可以直接使用 `create_react_agent` 或手写 ReAct 图。

执行循环：

```text
messages + tools
-> LLM
-> 如果没有 tool_calls，返回最终回答
-> 如果有 tool_calls，执行每个 tool
-> 把 tool result 加入 messages
-> 再次调用 LLM
-> 最多循环 N 次
```

伪代码：

```python
async def run_agent(messages, tools):
    for _ in range(5):
        response = await llm.ainvoke(messages, tools=to_openai_tools(tools))

        if not response.tool_calls:
            return response

        messages.append(response)

        for call in response.tool_calls:
            yield {"event": "tool_start", "data": {"name": call.name, "args": call.args}}

            tool = TOOL_REGISTRY[call.name]
            result = await tool.func(**call.args)

            yield {"event": "tool_result", "data": {"name": call.name, "content": result}}

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": str(result),
            })

    raise RuntimeError("Too many tool calls")
```

关键限制：

```text
必须设置最大循环次数，例如 5。
Tool 执行异常要转成 tool_result，而不是让整个请求崩掉。
Tool 入参必须用 schema 校验。
危险工具必须人工确认或禁用。
```

## 十六、阶段十一：前端 Tool 配置

目标：

- 用户能看到可用工具列表
- 用户能启用/禁用工具
- 用户能配置工具参数

前端可以先做成简单 JSON 编辑器：

```json
[
  {"type": "calculator", "enabled": true, "config": {}},
  {"type": "rag_search", "enabled": true, "config": {}}
]
```

后续再改成表单：

```text
[x] Calculator
[x] RAG Search
[ ] Web Search
```

推荐后端提供：

```http
GET /api/tools
```

返回：

```json
[
  {
    "type": "calculator",
    "name": "Calculator",
    "description": "Evaluate math expressions.",
    "config_schema": {}
  }
]
```

## 十七、流式响应设计

后端统一输出 SSE：

```python
def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
```

事件类型：

```text
metadata
返回 run_id。

token
返回模型增量 token。

tool_start
通知前端开始执行工具。

tool_result
通知前端工具执行结果。

plan
返回 Plan-Solve 生成的计划。

step_start
通知前端 Plan-Solve 当前开始执行哪一步。

step_result
通知前端 Plan-Solve 当前步骤执行结果。

checkpoint
返回当前 thread 的 checkpoint/next 摘要，方便前端显示“可继续执行”。

message
返回最终完整 assistant 消息。

error
返回错误信息。

end
流式结束。
```

前端状态建议：

```ts
type StreamStatus = "idle" | "inflight" | "done" | "error";

type StreamEvent =
  | { type: "token"; content: string }
  | { type: "tool_start"; name: string; args: unknown }
  | { type: "tool_result"; name: string; content: string }
  | { type: "plan"; steps: string[] }
  | { type: "step_start"; index: number; step: string }
  | { type: "step_result"; index: number; content: string }
  | { type: "checkpoint"; thread_id: string; next: string[] }
  | { type: "message"; message: Message };
```

前端收到 token 时：

```text
如果当前没有临时 assistant 消息，创建一个。
否则把 token append 到临时 assistant 消息 content。
```

收到 message 时：

```text
用后端返回的最终 message 替换临时消息。
```

## 十八、推荐开发顺序

严格按下面顺序做，不要跳：

### 1. 初始化 FastAPI 项目 -> 已完成

需要实现：

- 创建 `backend/app/main.py`
- 创建 FastAPI app
- 增加 `/health` 接口
- 配置 CORS，允许前端开发端口访问
- 配置基础异常处理
- 准备 `.env` 和配置读取模块

建议文件：

```text
backend/app/main.py
backend/app/config.py
backend/requirements.txt
```

验收标准：

- 启动后端服务
- 访问 `GET /health` 返回 `{"status": "ok"}`

### 2. 初始化 React 项目 -> 已完成

需要实现：

- 创建 Vite React TypeScript 项目
- 准备基础页面布局
- 增加聊天页面骨架
- 配置后端 API base URL
- 能从前端请求 `/health`

建议文件：

```text
frontend/src/App.tsx
frontend/src/api.ts
frontend/src/components/ChatPage.tsx
```

验收标准：

- 前端能启动
- 页面能显示基础聊天 UI
- 前端能成功请求后端健康检查接口

### 3. 初始化 LangChain LLM -> 已完成

需要实现：

- 创建 `llm.py`
- 从环境变量读取模型配置
- 初始化一个 LangChain chat model
- 第一版只支持一个模型，例如 OpenAI 或 Ollama
- 提供统一函数 `get_llm()`

建议接口：

```python
def get_llm():
    ...
```

建议文件：

```text
backend/app/llm.py
```

验收标准：

- 后端可以调用一次 LLM 并返回完整文本
- 模型 API key 或 base URL 由环境变量控制

### 4. 初始化 LangGraph checkpointer -> 完成

需要实现：

- 创建 `checkpoint.py`
- 选择第一版 checkpointer
- 本地学习阶段可以用 MemorySaver 或 SQLite
- 后续切换到mysql中
- 提供统一函数 `get_checkpointer()`

建议接口：

```python
def get_checkpointer():
    ...
```

建议文件：

```text
backend/app/checkpoint.py
```

验收标准：

- LangGraph graph 编译时可以传入 checkpointer
- 同一个 `thread_id` 多次调用时状态可以累积

### 5. 实现最小 Chat Graph -> 完成

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

### 6. 实现 SSE 流式 chat -> 完成

需要实现：

- 创建 `stream.py`
- 在后端增加 `POST /api/chat/stream`
- 使用 `graph.astream_events(...)`
- 把 LangGraph/LangChain 事件转换成 SSE
- 前端接收 token 并实时追加到页面

建议 SSE 事件：

```text
metadata
token
message
error
end
```

建议文件：

```text
backend/app/stream.py
backend/app/main.py
frontend/src/hooks/useChatStream.ts
frontend/src/components/ChatPage.tsx
```

验收标准：

- 用户输入问题后，前端能逐字或逐块显示回答
- 流结束后 loading 状态消失

### 7. 加数据库 thread/message 保存 ->完成

需要实现：

- 创建数据库连接
- 定义 Thread 和 Message 表
- 新增 thread 创建接口
- 新增 message 查询接口
- 用户消息发送前保存
- assistant 最终回答完成后保存

建议文件：

```text
backend/app/model/db.py
backend/app/model/models.py
backend/app/model/storage.py
backend/app/schemas.py
```

建议接口：

```http
POST /api/threads
GET /api/threads
GET /api/threads/{thread_id}/messages
```

验收标准：

- 创建 thread 后数据库有记录
- 发送消息后 message 表有 user 和 assistant 两条消息

### 8. 前端支持历史消息恢复 -> 完成

需要实现：

- 前端加载 thread 列表
- 点击 thread 后加载历史 messages
- 历史消息和当前流式消息合并展示
- 刷新页面后仍能恢复当前 thread 的消息

建议文件：

```text
frontend/src/hooks/useThreads.ts
frontend/src/hooks/useMessages.ts
frontend/src/components/ThreadList.tsx
frontend/src/components/MessageList.tsx
```

验收标准：

- 刷新页面后，历史对话仍显示
- 切换 thread 时显示对应 thread 的消息

### 9. 实现 thread state/checkpoint 查询接口 --> 完成

需要实现：

- 后端根据 `thread_id` 调用 `graph.aget_state(config)`
- 返回 `values`、`next`、`metadata` 等信息
- 可选实现 state history
- 前端可以查看当前 thread 是否有待继续节点

建议接口：

```http
GET /api/threads/{thread_id}/state
GET /api/threads/{thread_id}/history
```

建议文件：

```text
backend/app/storage.py
backend/app/main.py
```

验收标准：

- 调用 state 接口能看到 LangGraph 当前状态
- 同一个 thread_id 的 checkpoint 可被读取

### 10. 加文件上传接口  --> 完成

需要实现：

- 新增 `POST /api/files/upload`
- 接收 `multipart/form-data`
- 参数包含 `assistant_id` 或默认助手 ID
- 保存文件元信息
- 暂时可以先把原始文件保存到本地目录

建议文件：

```text
backend/app/uploads.py
backend/app/storage.py
frontend/src/components/FileUpload.tsx
```

验收标准：

- 前端能选择文件并上传
- 后端能保存文件记录和原始文件

### 11. 实现文件解析和切块 -> 完成

需要实现：

- 根据文件类型解析文本
- 支持 `.txt`、`.md`、`.pdf`、`.docx`
- 清理空字符和异常字符
- 使用 `RecursiveCharacterTextSplitter` 切块
- 每个 chunk 保留 metadata

建议文件：

```text
backend/app/parsing.py
backend/app/rag.py
```

验收标准：

- 上传文件后可以得到 chunk 列表
- 每个 chunk 有 `content`、`filename`、`assistant_id` 等 metadata

### 12. 接入向量库（Qdrant）->完成

需要实现：

- 初始化 embedding model
- 初始化 vector store
- 把 chunks 写入向量库
- metadata 中保存 `assistant_id`、`file_id`
- 提供 similarity search 函数

建议文件：

```text
backend/app/vectorstore.py
backend/app/rag.py
```

验收标准：

- 文件上传后 chunks 能写入向量库
- 输入 query 可以检索出相关 chunks

### 13. 实现 RAG 自动检索回答 -> 完成

需要实现：

- assistant 配置增加 `rag_enabled`
- chat graph 调用模型前先检索相关 chunks
- 把 context 注入 system prompt
- 如果没有检索结果，也要给模型明确说明
- 流式返回 RAG 答案

建议实现方式：

```text
mode=chat 且 rag_enabled=true
-> retrieve_context
-> call_model
```

验收标准：

- 上传文件后提问，回答能使用文件内容
- 没有相关内容时，回答不会硬编

### 14. 把 RAG search 注册成 LangChain tool -> 完成

需要实现：

- 创建 `rag_search` 工具
- 入参是 `query`
- 工具内部根据 assistant_id 检索向量库
- 返回简洁的文本或 chunk 列表
- 工具可被 ReAct 和 Plan-Solve 调用

建议文件：

```text
backend/app/tools.py
backend/app/rag.py
```

验收标准：

- 手动调用 `rag_search.invoke(...)` 能返回相关文件片段
- 工具 schema 能被 LLM 识别

### 15. 抽象 TOOL_REGISTRY 

需要实现：

- 定义统一工具注册表
- 每个工具有 type、name、description、args_schema、callable
- 根据 assistant.tools_config 加载启用工具
- 提供 `GET /api/tools` 给前端展示可用工具

建议文件：

```text
backend/app/tools.py
```

验收标准：

- 后端能列出所有可用工具
- assistant 可以只启用部分工具

### 16. 实现 calculator/current_time 工具

需要实现：

- `calculator`：执行安全的数学表达式
- `current_time`：返回当前时间
- 使用 LangChain `StructuredTool`
- 使用 Pydantic args schema
- 工具执行失败时返回可读错误

建议文件：

```text
backend/app/tools.py
```

验收标准：

- 工具可以单独 invoke
- 工具入参校验生效
- 工具错误不会导致后端崩溃

### 17. 实现 ReAct Graph

需要实现：

- 创建 `graph_react.py`
- 使用 `create_react_agent` 或手写 `StateGraph`
- LLM 绑定启用工具
- tool_calls 出现时进入 ToolNode
- 工具结果回到 messages
- 编译时接入 checkpointer

建议图结构：

```text
agent -> tools -> agent
agent -> END
```

建议文件：

```text
backend/app/graph_react.py
backend/app/agent.py
```

验收标准：

- 用户问计算问题时，模型能调用 calculator
- 工具结果进入 LangGraph state
- checkpoint 能恢复 ReAct 消息状态

### 18. 前端展示 tool_start/tool_result

需要实现：

- SSE 接收 `tool_start`
- SSE 接收 `tool_result`
- 在消息列表中展示工具调用过程
- 工具调用过程和 assistant 回答区分显示

建议文件：

```text
frontend/src/hooks/useChatStream.ts
frontend/src/components/ToolEvent.tsx
frontend/src/components/MessageList.tsx
```

验收标准：

- 前端能看到调用了哪个工具
- 前端能看到工具返回结果

### 19. 实现 Plan-Solve Graph

需要实现：

- 创建 `graph_plan_solve.py`
- 定义包含 `plan`、`current_step`、`observations`、`messages` 的 state
- planner 节点生成步骤计划
- executor 节点逐步执行计划
- solver 节点生成最终回答
- 支持调用 tools 或 rag_search
- 接入 checkpointer

建议图结构：

```text
planner -> executor -> executor -> solver -> END
```

建议文件：

```text
backend/app/graph_plan_solve.py
backend/app/agent.py
```

验收标准：

- 复杂问题会先生成 plan
- 每一步执行结果会保存到 observations
- 最终回答能总结计划执行结果

### 20. 前端展示 plan/step 事件

需要实现：

- SSE 接收 `plan`
- SSE 接收 `step_start`
- SSE 接收 `step_result`
- 前端用步骤列表展示 Plan-Solve 过程
- 当前步骤有 loading 状态

建议文件：

```text
frontend/src/components/PlanView.tsx
frontend/src/hooks/useChatStream.ts
```

验收标准：

- 用户能看到模型的计划
- 用户能看到每一步执行进度和结果

### 21. 前端实现 Agent Mode 配置

需要实现：

- assistant 配置中加入 `mode`
- UI 支持选择：
  - Chat
  - ReAct
  - Plan-Solve
- 不同 mode 显示不同说明
- 保存配置后，后端按 mode 选择 graph

建议文件：

```text
frontend/src/components/AgentModeConfig.tsx
backend/app/schemas.py
backend/app/agent.py
```

验收标准：

- 选择 Chat 时走 Chat Graph
- 选择 ReAct 时走 ReAct Graph
- 选择 Plan-Solve 时走 Plan-Solve Graph

### 22. 前端实现 Tool 配置 UI

需要实现：

- 请求 `GET /api/tools`
- 展示工具列表
- 每个工具支持启用/禁用
- 工具有配置项时展示表单或 JSON 编辑器
- 保存到 assistant.tools_config

建议文件：

```text
frontend/src/components/ToolConfig.tsx
frontend/src/api.ts
```

验收标准：

- 前端能启用 calculator
- 保存后 ReAct Graph 可以加载该工具

### 23. 增加错误处理和 loading 状态

需要实现：

- 后端统一返回 SSE error 事件
- LLM 调用失败时给前端安全错误信息
- Tool 调用失败时显示工具错误，不直接中断整个会话
- 前端支持 inflight/error/done 状态
- 支持用户中断当前流

建议文件：

```text
backend/app/stream.py
frontend/src/hooks/useChatStream.ts
frontend/src/components/MessageInput.tsx
```

验收标准：

- 网络错误时前端能提示
- LLM 错误时前端能结束 loading
- 用户可以停止当前响应

### 24. 再考虑认证、多模型、部署

需要实现：

- 简单登录或固定用户
- 多模型配置
- Dockerfile
- docker-compose
- 生产数据库迁移
- 日志和监控

建议延后原因：

- 这些不是核心问答能力
- 过早实现会干扰 Chat/RAG/Agent 主链路

验收标准：

- 本地核心功能稳定后，再进入这一阶段

## 十九、从 OpenGPTs 借鉴的内容

值得借鉴：

```text
assistant 和 thread 分离
配置驱动执行器
统一 run/stream 入口
SSE 流式事件
RAG 文件处理链路
Tool 注册表
LangGraph 图式编排
checkpoint 状态恢复
前端消息按 id 合并
```

暂时不要照搬或暂缓实现：

```text
ConfigurableField/config_schema 复杂动态 schema
多模型供应商
Bedrock XML agent
大量第三方工具
OIDC/JWT 认证
LangSmith feedback
public assistant
复杂 thread state editing
```

## 二十、第一版验收清单

Chat：

- 可以创建 thread
- 可以发送消息
- 可以流式显示回答
- 可以刷新后恢复历史
- Chat Graph 使用 LangGraph 实现
- 同一个 thread_id 可以从 checkpoint 恢复状态

RAG：

- 可以上传 txt/pdf/docx
- 可以成功切块入库
- 提问时可以检索相关片段
- 回答能引用上传内容
- 没有资料时能明确说明不知道

Tools：

- 后端有工具注册表
- assistant 能保存 tools_config
- 至少 calculator 工具可用
- 模型能调用工具并基于结果回答
- 前端能显示工具开始和工具结果
- RAG search 可以作为 tool 被 ReAct 调用

ReAct：

- assistant.mode 设置为 `react` 时走 ReAct Graph
- ReAct Graph 支持 tool_calls
- 工具结果会写回 LangGraph state
- checkpoint 中能看到 ReAct 执行后的 messages

Plan-Solve：

- assistant.mode 设置为 `plan_solve` 时走 Plan-Solve Graph
- 能生成 plan 事件
- 能逐步执行 step
- 能输出最终 answer
- checkpoint 中能恢复 plan、current_step、observations

Streaming：

- token 正常增量显示
- tool_start/tool_result 正常显示
- plan/step_start/step_result 正常显示
- checkpoint/next 状态可查询
- error 事件能显示错误
- end 事件能结束 loading

## 二十一、第二版可以增强的能力

当第一版稳定后，再考虑：

- 用户登录
- 多 assistant 管理
- Postgres + pgvector
- Web search 工具
- 代码执行工具
- 工具调用人工确认
- Plan-Solve 人工确认计划后再执行
- checkpoint 分支和回滚
- 引用来源展示
- 文档删除和重新索引
- 多模型切换
- Docker 部署
- 运行日志和 tracing

## 二十二、最小实现原则

实现时优先遵守：

```text
先跑通主链路，再抽象。
先做一个模型，再做多模型。
先做一个工具，再做工具平台。
先做一种文件格式，再扩展文件格式。
先用 LangGraph Memory/SQLite checkpoint 跑通，再切 Postgres checkpoint。
先做 ReAct，再做 Plan-Solve。
先用简单 UI，再做复杂配置页。
```

这个项目的核心不是“复制 OpenGPTs”，而是保留它的产品结构：

```text
Assistant = 配置
Thread = 一次对话
Message = 对话历史
RAG = 上传资料能力
Tool = 可配置外部能力
ReAct = 工具调用执行模式
Plan-Solve = 规划执行模式
Checkpoint = 图状态恢复
Stream = 用户体验
```
