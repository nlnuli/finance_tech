from mcp.server.fastmcp import FastMCP

from ..tools.tool import rag_search, run_calculator, run_current_time


def create_local_mcp_server() -> FastMCP:
    server = FastMCP(name="finance_tech_local_tools")

    @server.tool(
        name="rag_search",
        description="Search uploaded financial documents and return relevant chunks with source metadata.",
    )
    def rag_search_tool(query: str) -> str:
        return rag_search(query)

    @server.tool(
        name="calculator",
        description="Safely evaluate a basic math expression.",
    )
    def calculator_tool(expression: str) -> str:
        return run_calculator(expression)

    @server.tool(
        name="current_time",
        description="Return the current time for an IANA timezone.",
    )
    def current_time_tool(timezone: str = "Asia/Shanghai") -> str:
        return run_current_time(timezone)

    return server


def main() -> None:
    server = create_local_mcp_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
