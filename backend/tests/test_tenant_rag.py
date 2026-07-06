import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.tools import tool


class TenantRagTests(unittest.TestCase):
    def test_rag_search_uses_public_knowledge_base(self):
        with (
            patch.object(tool, "get_settings", return_value=SimpleNamespace(rag_final_count=4)),
            patch.object(
                tool,
                "similarity_search",
                return_value=[
                    {
                        "content": "Revenue grew.",
                        "metadata": {
                            "filename": "report.pdf",
                            "file_id": 7,
                            "chunk_index": 0,
                        },
                        "score": 0.8,
                    }
                ],
            ) as search,
        ):
            result = tool.rag_search("revenue")

        search.assert_called_once_with(query="revenue", k=4)
        self.assertIn("Revenue grew.", result)


if __name__ == "__main__":
    unittest.main()
