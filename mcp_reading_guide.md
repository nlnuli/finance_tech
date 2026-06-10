# MCP 逻辑阅读导览

这份文档用于人工阅读当前项目里的 MCP 实现。建议按下面顺序看代码，这样能先建立主调用链，再补局部细节。

## 0. 先确认 Git 状态

当前 `first_version` 分支最新已推送提交是：

```text
f1244bd 新增错误兼容等逻辑
```

MCP 相关代码目前主要是工作区未提交改动，不完全属于这个最新提交。阅读时如果用 `git show HEAD` 找不到 MCP 文件，是正常的。

关键新增/改动位置：

- `backend/app/mcp/`
- `backend/app/runtime.py`
- `backend/mcp_servers.json`
- `backend/app/main.py`
- `backend/app/graph_react.py`
- `backend/app/graph_plan_solve.py`
- `backend/app/tools/fast_api.py`
- `frontend/src/api.ts`
- `frontend/src/components/ToolsPage.tsx`

## 1. 启动入口：FastAPI lifespan

先看：

```text
backend/app/main.py
```

重点看 `lifespan`：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.services = await build_app_services()
    yield
```

这里说明 MCP 初始化不是在模块 import 阶段完成，而是在 FastAPI 应用启动阶段完成。原因是 MCP tool discovery 是异步过程，需要在运行时初始化。

## 2. 服务组装：runtime.py

再看：

```text
backend/app/runtime.py
```

核心流程：

```text
build_app_services()
  -> get_settings()
  -> McpToolProvider(settings)
  -> await mcp_provider.initialize()
  -> tools = mcp_provider.get_tool_callables()
  -> create_react_graph(tools)
  -> create_plan_solve_graph(tools)
  -> ChatStrategy(...)
```

这个文件是 MCP 和 LangGraph 之间的连接点。

可以把它理解为：

```text
MCP provider 负责发现工具
runtime.py 负责把工具注入 graph
graph 负责在对话中真正使用工具
```

## 3. MCP 配置模型

看：

```text
backend/app/mcp/config.py
```

这里定义三类核心模型：

- `McpStdioServerConfig`
- `McpHttpServerConfig`
- `McpToolMetadata`

当前支持两种 transport：

```text
stdio
http
```

工具来源分两类：

```text
local_mcp
external_mcp
```

`McpToolMetadata` 是 `/api/tools` 返回给前端展示的数据结构，里面有：

- `name`
- `description`
- `args_schema`
- `source`
- `server_name`
- `transport`

## 4. MCP 核心：provider.py

重点看：

```text
backend/app/mcp/provider.py
```

核心类是：

```python
class McpToolProvider:
```

重点读 `initialize()`。它做了这些事：

1. 读取 MCP server 配置。
2. 自动追加一个本地 MCP server。
3. 创建 `MultiServerMCPClient`。
4. 逐个 server 拉取工具列表。
5. 检查工具名是否重复。
6. 把 MCP tools 转成 LangChain tools。
7. 缓存可调用工具和展示 metadata。

关键字段：

```python
self.tools
self.tool_metadata
```

二者用途不同：

```text
self.tools         -> 给 agent / graph 调用
self.tool_metadata -> 给 /api/tools 和前端展示
```

外部 MCP server 加载失败时会跳过。本地 MCP server 加载失败时会直接抛错，因为本地工具被视为必需能力。

## 5. 本地 MCP server

看：

```text
backend/app/mcp/local_server.py
```

这里用 `FastMCP` 把项目内已有函数包装成 MCP tools：

```text
rag_search
calculator
current_time
```

实际业务逻辑还在：

```text
backend/app/tools/tool.py
```

也就是说，本地 MCP server 不是重新实现工具，而是把已有 Python 函数通过 MCP 协议暴露出来。

本地 server 通过 stdio 启动：

```python
server.run(transport="stdio")
```

provider 中对应的启动命令是：

```python
command=sys.executable
args=["-m", "app.mcp.local_server"]
```

## 6. ReAct graph 如何使用 MCP tools

看：

```text
backend/app/graph_react.py
```

核心函数：

```python
def create_react_graph(tools: list):
    return create_react_agent(
        get_llm(),
        tools,
        checkpointer=get_checkpointer(),
        prompt=REACT_PROMPT,
    )
```

这里没有 MCP 细节。它只关心传进来的 `tools` 是否符合 LangChain tool 接口。

MCP 细节已经被 `langchain-mcp-adapters` 和 `McpToolProvider` 隐藏掉了。

## 7. Plan-Solve graph 如何使用 MCP tools

看：

```text
backend/app/graph_plan_solve.py
```

重点看：

```python
class ExecutorNode:
```

初始化时会把工具列表转成字典：

```python
self.tools = {tool.name: tool for tool in tools}
```

执行每个 plan step 时，LLM 先输出工具决策：

```json
{"tool":"工具名","input":{"参数名":"参数值"},"answer":""}
```

如果工具存在，就执行：

```python
tool_result = await tool.ainvoke(tool_input, config=config)
```

所以 Plan-Solve 模式不是用 LangGraph 预置 ReAct agent，而是自己让 LLM 产出 JSON 决策，再手动调用工具。

## 8. 聊天流入口和 SSE 事件

看：

```text
backend/app/stream.py
```

重点链路：

```text
/api/chat/stream
  -> chat_event_stream()
  -> get_app_services(app).chat_strategy
  -> select_graph_input(...)
  -> graph.astream_events(...)
```

工具相关事件会被转成 SSE：

```text
tool_start
tool_result
```

Plan-Solve 还会额外输出：

```text
plan
step_start
step_result
```

这也是前端能够显示工具调用过程和计划步骤的原因。

## 9. 工具列表接口

看：

```text
backend/app/tools/fast_api.py
```

现在 `/api/tools` 不再读旧的 registry，而是：

```python
provider = get_app_services(request.app).mcp_provider
return provider.list_tools(enabled_names)
```

所以工具展示的真实来源已经变成 MCP provider。

## 10. 外部 MCP server 配置

看：

```text
backend/mcp_servers.json
```

当前默认内容是：

```json
{
  "servers": []
}
```

也就是说，不额外配置时，只有本地 MCP server 提供的三个工具。

如果要加外部 HTTP MCP server，可以写成：

```json
{
  "servers": [
    {
      "name": "weather",
      "transport": "http",
      "enabled": true,
      "url": "http://127.0.0.1:9000/mcp"
    }
  ]
}
```

也可以通过环境变量指定配置文件路径：

```text
MCP_CONFIG_PATH
```

定义位置：

```text
backend/app/config.py
```

## 11. 前端展示

看：

```text
frontend/src/api.ts
frontend/src/components/ToolsPage.tsx
```

`ToolInfo` 现在新增了：

```text
source
server_name
transport
```

`ToolsPage` 会展示工具来自本地 MCP 还是外部 MCP。

## 12. 旧工具系统现在的角色

看：

```text
backend/app/tools/registry.py
```

这个文件现在只是兼容保留层，避免旧代码 import 报错。

真实工具来源已经迁移到：

```text
backend/app/mcp/provider.py
```

工具业务函数仍在：

```text
backend/app/tools/tool.py
```

但它们不再直接注册为 LangChain tools，而是先被 `local_server.py` 包装成 MCP tools，再由 provider 转回 LangChain tools 给 agent 使用。

## 13. 总调用链

可以用下面这条链路理解整个 MCP 实现：

```text
FastAPI 启动
  -> lifespan
  -> build_app_services()
  -> McpToolProvider.initialize()
  -> 加载 local MCP server + external MCP servers
  -> MultiServerMCPClient 获取 tools
  -> tools 注入 create_react_graph / create_plan_solve_graph
  -> 用户请求 /api/chat/stream
  -> graph 执行
  -> agent 调用 LangChain tool
  -> LangChain MCP adapter 调 MCP server
  -> MCP server 执行真实工具函数
  -> 工具结果返回 graph
  -> stream.py 转成 SSE 发给前端
```

## 14. 阅读时抓住的主线

最重要的一句话：

```text
MCP provider 在应用启动时发现所有工具，把它们转换成 LangChain tools，然后依赖注入给不同 LangGraph agent 使用。
```

理解这句话后，再看每个文件会清楚很多：

- `main.py`：什么时候初始化
- `runtime.py`：如何组装服务和注入工具
- `mcp/provider.py`：从哪里发现工具
- `mcp/local_server.py`：本地工具怎么变成 MCP tool
- `graph_react.py`：ReAct 怎么直接使用 tools
- `graph_plan_solve.py`：Plan-Solve 怎么手动调用 tools
- `stream.py`：工具执行过程怎么流式返回前端
- `tools/fast_api.py`：工具列表怎么展示

## 15. 当前实现注意点

- MCP 配置是启动时加载，修改后需要重启后端。
- 本地 MCP server 是必需的，初始化失败会导致后端启动失败。
- 外部 MCP server 是可选的，失败会跳过并记录 warning。
- 所有 MCP server 的工具名必须全局唯一。
- `/api/tools` 展示的是 provider 缓存的 metadata，不直接触发重新发现。
- `backend/mcp_servers.json` 当前为空，因此默认只有 `rag_search`、`calculator`、`current_time`。
