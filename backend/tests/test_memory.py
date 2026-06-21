import asyncio
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from app.memory.service import (
    MemoryEntry,
    MemoryStore,
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

            self.assertIn("用户偏好中文回答", index)
            self.assertNotIn("用户偏好英文回答", index)
            self.assertNotIn("已归档主题", index)

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

    def test_retrieve_memory_brief_updates_usage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self.make_store(Path(tmpdir))
            entry = store.make_entry(
                "user-profile",
                "user_profile",
                "用户主要关注美股 AI 基础设施公司。",
                0.9,
            )
            store.write_topic_entries("default", "user-profile", [entry])

            brief = store.retrieve_memory_brief("请分析 AI 基础设施公司", "default")
            updated = store.load_entries("default")["user-profile"][0]

            self.assertIn("AI 基础设施", brief)
            self.assertEqual(updated.metadata["use_count"], "1")


if __name__ == "__main__":
    unittest.main()
