from functools import lru_cache

from langgraph.checkpoint.memory import InMemorySaver


@lru_cache(maxsize=1)
def get_checkpointer() -> InMemorySaver:
    return InMemorySaver()
