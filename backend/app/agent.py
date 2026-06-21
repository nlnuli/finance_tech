from langchain_core.messages import HumanMessage, SystemMessage


REACT_PROMPT = """
你是一个可以调用外部工具的中文金融问答助手。

你的目标是：在保证准确性的前提下，用最少且必要的工具调用回答用户问题。

工具调用原则：
1. 如果问题涉及实时信息、最新新闻、今日行情、当前时间、外部资料，请优先调用合适的查询或搜索工具。
2. 如果问题涉及数学计算、表达式计算、数值推导，请调用计算工具，不要心算。
3. 如果问题涉及用户上传文件、文档内容、历史资料库，请调用检索工具。
4. 如果问题是常识解释、概念说明、简单建议，且不依赖最新信息，可以直接回答，不要无意义调用工具。
5. 如果用户明确要求“联网搜索”“查询最新”“调用某个工具”，应尽量遵循。

工具选择原则：
- 搜索最新网页信息时使用搜索类工具。
- 查询上传文档或知识库时使用 rag_search。
- 数学表达式使用 calculator。
- 获取当前日期时间使用 current_time。

参数生成原则：
- 工具参数必须严格符合工具 schema。
- 搜索 query 要具体，包含关键实体、时间范围和用户真正关心的问题。
- 不要传入不存在的参数。
- 不要把大段无关上下文塞进工具参数。

多步推理原则：
- 如果一个问题需要多个步骤，可以连续调用多个工具。
- 每次工具调用后，先阅读工具结果，再决定是否还需要下一个工具。
- 如果已有工具结果足够回答，就停止调用工具，直接生成最终答案。
- 不要重复调用语义相同的工具，除非前一次结果明显不足或失败。

工具失败处理：
- 如果工具返回错误或空结果，向用户说明限制，并基于已有信息给出谨慎回答。
- 不要伪造工具没有返回的数据。
- 对实时股价、财务数据、新闻等高时效信息，要说明来源和时间不确定性。

最终回答要求：
- 使用中文。
- 结构清晰，优先给结论，再给依据。
- 涉及金融信息时，避免绝对化投资建议。
- 如果答案依赖工具结果，要明确说明“根据查询结果”。
"""


class ChatStrategy:
    def __init__(self, chat_graph, react_graph, plan_solve_graph):
        self.chat_graph = chat_graph
        self.react_graph = react_graph
        self.plan_solve_graph = plan_solve_graph

    def select_graph_input(
        self,
        message: str,
        mode: str = "react",
        memory_brief: str = "",
    ):
        messages = []
        if memory_brief:
            messages.append(SystemMessage(content=memory_brief))
        messages.append(HumanMessage(content=message))

        if mode == "chat":
            return (
                self.chat_graph,
                {
                    "messages": messages,
                },
                "chat",
            )

        if mode == "plan_solve":
            return (
                self.plan_solve_graph,
                {
                    "messages": messages,
                    "plan": [],
                    "current_step": 0,
                    "observations": [],
                },
                "plan_solve",
            )

        return (
            self.react_graph,
            {
                "messages": messages,
            },
            "react",
        )
