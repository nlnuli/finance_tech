from __future__ import annotations

import sys
import types


def patch_ragas_vertexai_import() -> None:
    """Patch a Ragas 0.4 import edge when VertexAI extras are not installed.

    Ragas 0.4 imports ChatVertexAI while building its generic LLM support.
    This project evaluates with the configured OpenAI-compatible model, so the
    VertexAI class only needs to exist for import-time type checks.
    """

    module_name = "langchain_community.chat_models.vertexai"
    if module_name in sys.modules:
        return

    module = types.ModuleType(module_name)

    class ChatVertexAI:  # pragma: no cover - import-time compatibility shim
        pass

    module.ChatVertexAI = ChatVertexAI
    sys.modules[module_name] = module
