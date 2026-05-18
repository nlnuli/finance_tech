# 建立一个langchain llm model
import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 加载环境变量
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# def create_llm() -> ChatOpenAI:
#     api_key = os.getenv("OPENAI_API_KEY")
#     if not api_key:
#         raise RuntimeError("OPENAI_API_KEY is not set in backend/.env")

#     return ChatOpenAI(
#         model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
#         temperature=0.7,
#         api_key=api_key,
#     )


# def main() -> None:
#     llm = create_llm()
#     response = llm.invoke("What is the capital of France?")
#     print(response.content)


# if __name__ == "__main__":
#     main()
# api_key = os.getenv("OPENAI_API_KEY")
# llm = ChatOpenAI(
#         model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
#         temperature=0.7,
#         api_key=api_key,
# )
# response = llm.invoke("What is the capital of France?")
# print(response.content)

@lru_cache(maxsize=3)
def create_llm() -> ChatOpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in backend/.env")

    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
        temperature=0.7,
        api_key=api_key,
    )

