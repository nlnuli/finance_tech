import asyncio
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from app.memory.service import (
    MemoryEntry,
    MemoryStore,
    parse_memory_index,
    parse_memory_entries,
    serialize_memory_entry,
)


class MemoryStoreTest(unittest.TestCase):
    def make_store(self, root: Path) -> MemoryStore:
        store = MemoryStore(memory_dir=root)
        store.trigger_message_count = 3
        return store

    def test_initializes_user_scoped_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self.make_store(Path(tmpdir))
            store.initialize_user("alice")
            store.initialize_user("bob")

            self.assertTrue(
                (Path(tmpdir) / "users" / "alice" / "MEMORY.md").exists()
            )
            self.assertTrue(
                (Path(tmpdir) / "users" / "bob" / "user-profile.md").exists()
            )

    def test_parse_and_serialize_markdown_entry(self):
        entry = MemoryEntry(
            id="mem_20260618010101_test",
            topic="user-profile",
            metadata={
                "status": "active",
                "source": "auto",
                "kind": "user_profile",
                "confidence": "0.82",
            },
            body="用户主要关注美股 AI 基础设施公司。",
        )
        text = serialize_memory_entry(entry)
        parsed = parse_memory_entries("# User Profile\n\n" + text, "user-profile")

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].id, entry.id)
        self.assertEqual(parsed[0].metadata["status"], "active")
        self.assertEqual(parsed[0].body, entry.body)

    def test_rebuild_index_excludes_deprecated_and_archived(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self.make_store(Path(tmpdir))
            active = store.make_entry(
                "user-profile",
                "user_profile",
                "用户偏好中文回答。",
                0.9,
            )
            deprecated = store.make_entry(
                "user-profile",
                "user_profile",
                "用户偏好英文回答。",
                0.9,
            )
            deprecated.metadata["status"] = "deprecated"
            archived = store.make_entry(
                "user-profile",
                "user_profile",
                "用户曾关注某个已归档主题。",
                0.9,
            )
            archived.metadata["status"] = "archived"

            store.write_topic_entries("default", "user-profile", [active, deprecated])
            store.write_topic_entries("default", "archive", [archived])
            index = store.rebuild_index("default")

            self.assertIn(f"id={active.id}", index)
            self.assertIn("topic=user-profile", index)
            self.assertIn("status=active", index)
            self.assertIn("kind=user_profile", index)
            self.assertIn(f"ref=user-profile.md#{active.id}", index)
            self.assertIn("keywords=", index)
            self.assertIn("brief: 用户偏好中文回答", index)
            self.assertIn("用户偏好中文回答", index)
            self.assertNotIn("用户偏好英文回答", index)
            self.assertNotIn("已归档主题", index)

            items = parse_memory_index(index)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].id, active.id)
            self.assertEqual(items[0].topic, "user-profile")

    def test_financial_insight_expiry_becomes_stale(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self.make_store(Path(tmpdir))
            entry = store.make_entry(
                "financial-insights",
                "financial_insight",
                "截至测试日期，用户关注云厂商 AI capex。",
                0.9,
            )
            entry.metadata["expires_at"] = (
                date.today() - timedelta(days=1)
            ).isoformat()
            store.write_topic_entries("default", "financial-insights", [entry])

            store.compact("default")
            entries = store.load_entries("default")["financial-insights"]

            self.assertEqual(entries[0].metadata["status"], "stale")

    def test_auto_update_threshold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self.make_store(Path(tmpdir))

            async def fake_extract(messages):
                return [
                    store.make_entry(
                        "user-profile",
                        "user_profile",
                        "用户主要关注美股 AI 基础设施公司。",
                        0.82,
                    )
                ]

            messages = [
                {"id": 1, "role": "user", "content": "a"},
                {"id": 2, "role": "assistant", "content": "b"},
            ]
            with patch(
                "app.memory.service.storage.list_messages_after",
                return_value=messages,
            ):
                result = asyncio.run(store.run_auto_update("default"))
            self.assertEqual(result["added"], 0)
            self.assertEqual(result["pending"], 2)

            messages.append({"id": 3, "role": "user", "content": "c"})
            store.extract_memory_candidates = fake_extract
            with patch(
                "app.memory.service.storage.list_messages_after",
                return_value=messages,
            ):
                result = asyncio.run(store.run_auto_update("default"))

            self.assertEqual(result["added"], 1)
            state = store.read_state("default")
            self.assertEqual(state["last_processed_message_id"], 3)

    def test_retrieve_memory_context_loads_full_entry_and_updates_usage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self.make_store(Path(tmpdir))
            entry = store.make_entry(
                "user-profile",
                "user_profile",
                "用户主要关注美股 AI 基础设施公司。\n完整细节：偏好跟踪 capex、毛利率和订单能见度。",
                0.9,
            )
            store.write_topic_entries("default", "user-profile", [entry])
            store.rebuild_index("default")

            brief = store.retrieve_memory_brief("请分析 AI 基础设施公司", "default")
            updated = store.load_entries("default")["user-profile"][0]

            self.assertIn("# Relevant Long-Term Memory", brief)
            self.assertIn("AI 基础设施", brief)
            self.assertIn("完整细节：偏好跟踪 capex、毛利率和订单能见度", brief)
            self.assertEqual(updated.metadata["use_count"], "1")

    def test_llm_brief_and_keywords_only_write_to_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self.make_store(Path(tmpdir))

            class FakeResponse:
                content = (
                    "["
                    "{"
                    '"topic": "user-profile", '
                    '"kind": "user_profile", '
                    '"content": "用户长期关注美股 AI 基础设施公司。", '
                    '"brief": "关注美股 AI 基础设施公司", '
                    '"keywords": ["美股", "AI基础设施", "长期关注"], '
                    '"confidence": 0.88'
                    "}"
                    "]"
                )

            class FakeLLM:
                async def ainvoke(self, messages):
                    return FakeResponse()

            with patch("app.memory.service.get_llm", return_value=FakeLLM()):
                entries = asyncio.run(
                    store.extract_llm_entries(
                        [{"id": 1, "role": "user", "content": "总结我的偏好"}]
                    )
                )

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].index_brief, "关注美股 AI 基础设施公司")
            self.assertEqual(entries[0].index_keywords[0], "美股")
            self.assertNotIn("brief", entries[0].metadata)
            self.assertNotIn("keywords", entries[0].metadata)

            store.append_entries("default", entries)
            index = store.index_path("default").read_text(encoding="utf-8")
            topic = store.read_topic("default", "user-profile")

            self.assertIn("brief: 关注美股 AI 基础设施公司", index)
            self.assertIn("keywords=美股,AI基础设施,长期关注", index)
            self.assertNotIn("brief:", topic)
            self.assertNotIn("keywords:", topic)


if __name__ == "__main__":
    unittest.main()
