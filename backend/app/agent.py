from langchain_core.messages import HumanMessage


REACT_PROMPT = """
你是一个有能力调用外部工具的智能助手。

你可以根据用户问题决定是否调用工具：
- 如果问题需要查询、计算、检索或执行操作，请调用合适的工具。
- 如果问题可以直接回答，则直接回答。
- 不要编造工具结果。
- 工具返回后，请基于工具结果给出最终答案。
- 最终答案使用中文，结构清晰、简洁准确。
"""


class ChatStrategy:
    def __init__(self, chat_graph, react_graph, plan_solve_graph):
        self.chat_graph = chat_graph
        self.react_graph = react_graph
        self.plan_solve_graph = plan_solve_graph

    def select_graph_input(self, message: str, mode: str = "react"):
        if mode == "chat":
            return (
                self.chat_graph,
                {
                    "messages": [HumanMessage(content=message)],
                },
                "chat",
            )

        if mode == "plan_solve":
            return (
                self.plan_solve_graph,
                {
                    "messages": [HumanMessage(content=message)],
                    "plan": [],
                    "current_step": 0,
                    "observations": [],
                },
                "plan_solve",
            )

        return (
            self.react_graph,
            {
                "messages": [HumanMessage(content=message)],
            },
            "react",
        )
