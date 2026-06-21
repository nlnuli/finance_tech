import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from ..config import Settings, get_settings
from ..llm import get_llm
from ..model import storage


TOPIC_FILES = {
    "user-profile": "user-profile.md",
    "financial-insights": "financial-insights.md",
    "finance-style": "finance-style.md",
    "workflows": "workflows.md",
}
SPECIAL_FILES = {
    "deprecated": "deprecated.md",
    "archive": "archive.md",
}
ALL_TOPIC_FILES = {**TOPIC_FILES, **SPECIAL_FILES}
INDEX_FILENAME = "MEMORY.md"
STATE_FILENAME = ".state.json"
METADATA_KEYS = {
    "status",
    "source",
    "kind",
    "confidence",
    "created_at",
    "updated_at",
    "last_used_at",
    "use_count",
    "as_of_date",
    "expires_at",
    "supersedes",
    "superseded_by",
}
ACTIVE_STATUSES = {"active", "stale"}
EXPLICIT_MEMORY_MARKERS = (
    "记住",
    "以后都",
    "我偏好",
    "我的偏好",
    "不要再",
    "不再",
    "以后不用",
)
CORRECTION_MARKERS = ("不要再", "不再", "以后不用", "改成", "替换为")


@dataclass
class MemoryEntry:
    id: str
    topic: str
    metadata: dict[str, str] = field(default_factory=dict)
    body: str = ""

    @property
    def status(self) -> str:
        return self.metadata.get("status", "active")

    @property
    def source(self) -> str:
        return self.metadata.get("source", "auto")

    @property
    def kind(self) -> str:
        return self.metadata.get("kind", "note")


def today_iso() -> str:
    return date.today().isoformat()


def now_id_stamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def safe_user_id(user_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", user_id.strip())
    safe = safe.strip("._")
    return safe or "default"


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "-", value.strip())
    value = value.strip("-")
    return value[:32] or "memory"


def parse_iso_date(value: str | None) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def parse_number(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def parse_int(value: str | None, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except ValueError:
        return default


def parse_memory_entries(text: str, topic: str) -> list[MemoryEntry]:
    entries: list[MemoryEntry] = []
    lines = text.splitlines()
    current_id: Optional[str] = None
    current_lines: list[str] = []

    def flush() -> None:
        if not current_id:
            return
        entries.append(parse_entry_block(current_id, current_lines, topic))

    for line in lines:
        if line.startswith("## mem_"):
            flush()
            current_id = line.removeprefix("## ").strip()
            current_lines = []
        elif current_id:
            current_lines.append(line)

    flush()
    return entries


def parse_entry_block(entry_id: str, lines: list[str], topic: str) -> MemoryEntry:
    metadata: dict[str, str] = {}
    body_lines: list[str] = []
    reading_metadata = True

    for line in lines:
        stripped = line.strip()
        if reading_metadata and not stripped:
            continue
        if reading_metadata and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            if key in METADATA_KEYS:
                metadata[key] = value.strip()
                continue
        reading_metadata = False
        body_lines.append(line)

    return MemoryEntry(
        id=entry_id,
        topic=topic,
        metadata=metadata,
        body="\n".join(body_lines).strip(),
    )


def serialize_memory_entry(entry: MemoryEntry) -> str:
    ordered_keys = [
        "status",
        "source",
        "kind",
        "confidence",
        "created_at",
        "updated_at",
        "last_used_at",
        "use_count",
        "as_of_date",
        "expires_at",
        "supersedes",
        "superseded_by",
    ]
    lines = [f"## {entry.id}"]
    for key in ordered_keys:
        value = entry.metadata.get(key)
        if value not in (None, ""):
            lines.append(f"{key}: {value}")
    for key, value in sorted(entry.metadata.items()):
        if key not in ordered_keys and value not in (None, ""):
            lines.append(f"{key}: {value}")
    lines.extend(["", entry.body.strip(), ""])
    return "\n".join(lines).rstrip() + "\n"


class MemoryStore:
    def __init__(
        self,
        settings: Settings | None = None,
        memory_dir: Path | str | None = None,
    ):
        self.settings = settings or get_settings()
        self.enabled = bool(self.settings.memory_enabled)
        self.root = Path(memory_dir or self.settings.memory_dir)
        self.trigger_message_count = max(
            1,
            int(self.settings.memory_auto_trigger_message_count),
        )
        self.index_max_lines = max(20, int(self.settings.memory_index_max_lines))
        self.index_max_bytes = max(1024, int(self.settings.memory_index_max_bytes))

    def user_id(self, user_id: str | None = None) -> str:
        return safe_user_id(user_id or self.settings.memory_default_user_id)

    def user_dir(self, user_id: str | None = None) -> Path:
        return self.root / "users" / self.user_id(user_id)

    def state_path(self, user_id: str | None = None) -> Path:
        return self.user_dir(user_id) / STATE_FILENAME

    def topic_path(self, user_id: str | None, topic: str) -> Path:
        filename = ALL_TOPIC_FILES.get(topic)
        if filename is None:
            raise ValueError(f"Unknown memory topic: {topic}")
        return self.user_dir(user_id) / filename

    def index_path(self, user_id: str | None = None) -> Path:
        return self.user_dir(user_id) / INDEX_FILENAME

    def initialize_user(self, user_id: str | None = None) -> None:
        if not self.enabled:
            return
        user_dir = self.user_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        for topic, filename in ALL_TOPIC_FILES.items():
            path = user_dir / filename
            if not path.exists():
                path.write_text(self.default_topic_text(topic), encoding="utf-8")
        if not self.index_path(user_id).exists():
            self.index_path(user_id).write_text("# Memory Index\n\n", encoding="utf-8")
            self.rebuild_index(user_id)
        if not self.state_path(user_id).exists():
            self.write_state(user_id, {"last_processed_message_id": 0})

    def default_topic_text(self, topic: str) -> str:
        titles = {
            "user-profile": "User Profile",
            "financial-insights": "Financial Insights",
            "finance-style": "Finance Style",
            "workflows": "Workflows",
            "deprecated": "Deprecated Memory",
            "archive": "Archived Memory",
        }
        return f"# {titles.get(topic, topic)}\n\n"

    def read_state(self, user_id: str | None = None) -> dict[str, Any]:
        self.initialize_user(user_id)
        path = self.state_path(user_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return {"last_processed_message_id": 0}

    def write_state(self, user_id: str | None, state: dict[str, Any]) -> None:
        path = self.state_path(user_id)
        path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def read_topic(self, user_id: str | None, topic: str) -> str:
        self.initialize_user(user_id)
        return self.topic_path(user_id, topic).read_text(encoding="utf-8")

    def write_topic_entries(
        self,
        user_id: str | None,
        topic: str,
        entries: list[MemoryEntry],
    ) -> None:
        self.initialize_user(user_id)
        text = self.default_topic_text(topic)
        if entries:
            text += "\n".join(serialize_memory_entry(entry) for entry in entries)
        self.topic_path(user_id, topic).write_text(text, encoding="utf-8")

    def load_entries(
        self,
        user_id: str | None = None,
        include_special: bool = False,
    ) -> dict[str, list[MemoryEntry]]:
        self.initialize_user(user_id)
        topics = ALL_TOPIC_FILES if include_special else TOPIC_FILES
        return {
            topic: parse_memory_entries(self.read_topic(user_id, topic), topic)
            for topic in topics
        }

    def append_entries(
        self,
        user_id: str | None,
        entries: list[MemoryEntry],
    ) -> int:
        if not entries:
            return 0
        existing_by_topic = self.load_entries(user_id, include_special=True)
        added = 0
        for entry in entries:
            topic_entries = existing_by_topic.setdefault(entry.topic, [])
            if self.has_duplicate(topic_entries, entry):
                continue
            self.apply_supersede_if_needed(existing_by_topic, entry)
            topic_entries.append(entry)
            added += 1
        for topic, entries_for_topic in existing_by_topic.items():
            self.write_topic_entries(user_id, topic, entries_for_topic)
        self.compact(user_id)
        return added

    def has_duplicate(self, existing: list[MemoryEntry], candidate: MemoryEntry) -> bool:
        candidate_text = normalize_text(candidate.body)
        if not candidate_text:
            return True
        for entry in existing:
            if entry.status not in ACTIVE_STATUSES:
                continue
            entry_text = normalize_text(entry.body)
            if candidate_text == entry_text:
                entry.metadata["updated_at"] = today_iso()
                return True
            if candidate_text in entry_text or entry_text in candidate_text:
                entry.metadata["updated_at"] = today_iso()
                if len(candidate.body) > len(entry.body):
                    entry.body = candidate.body
                return True
        return False

    def apply_supersede_if_needed(
        self,
        existing_by_topic: dict[str, list[MemoryEntry]],
        candidate: MemoryEntry,
    ) -> None:
        if not any(marker in candidate.body for marker in CORRECTION_MARKERS):
            return
        candidate_terms = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", candidate.body))
        if not candidate_terms:
            return
        supersedes = []
        for entry in existing_by_topic.get(candidate.topic, []):
            if entry.status != "active" or entry.id == candidate.id:
                continue
            entry_terms = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", entry.body))
            if candidate_terms & entry_terms:
                entry.metadata["status"] = "deprecated"
                entry.metadata["updated_at"] = today_iso()
                entry.metadata["superseded_by"] = candidate.id
                supersedes.append(entry.id)
        if supersedes:
            candidate.metadata["supersedes"] = ", ".join(supersedes)

    def rebuild_index(self, user_id: str | None = None) -> str:
        self.initialize_files_only(user_id)
        entries_by_topic = self.load_entries(user_id)
        lines = [
            "# Memory Index",
            "",
            "This file is an index. Load topic files only when relevant.",
            "",
        ]
        for topic, filename in TOPIC_FILES.items():
            lines.extend([f"## {filename}", ""])
            topic_entries = [
                entry
                for entry in entries_by_topic.get(topic, [])
                if entry.status in ACTIVE_STATUSES
            ]
            if not topic_entries:
                lines.append("- No active memory.")
            else:
                for entry in topic_entries:
                    summary = self.entry_summary(entry)
                    lines.append(
                        f"- `{entry.status}` {summary} -> "
                        f"{filename}#{entry.id}"
                    )
            lines.append("")

        text = "\n".join(lines).strip() + "\n"
        text = self.trim_index(text)
        self.index_path(user_id).write_text(text, encoding="utf-8")
        return text

    def initialize_files_only(self, user_id: str | None = None) -> None:
        user_dir = self.user_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        for topic, filename in ALL_TOPIC_FILES.items():
            path = user_dir / filename
            if not path.exists():
                path.write_text(self.default_topic_text(topic), encoding="utf-8")

    def trim_index(self, text: str) -> str:
        lines = text.splitlines()[: self.index_max_lines]
        text = "\n".join(lines).strip() + "\n"
        encoded = text.encode("utf-8")
        if len(encoded) <= self.index_max_bytes:
            return text
        return encoded[: self.index_max_bytes].decode("utf-8", errors="ignore")

    def entry_summary(self, entry: MemoryEntry) -> str:
        first_line = next(
            (line.strip() for line in entry.body.splitlines() if line.strip()),
            "",
        )
        return first_line[:160]

    def compact(self, user_id: str | None = None) -> dict[str, int]:
        if not self.enabled:
            return {"disabled": 1}
        entries_by_topic = self.load_entries(user_id, include_special=True)
        today = date.today()
        changed = {"stale": 0, "deprecated": 0, "archived": 0}

        for topic, entries in list(entries_by_topic.items()):
            if topic in SPECIAL_FILES:
                continue
            for entry in entries:
                if entry.source == "manual":
                    continue
                status = entry.status
                expires_at = parse_iso_date(entry.metadata.get("expires_at"))
                last_used = parse_iso_date(
                    entry.metadata.get("last_used_at")
                    or entry.metadata.get("updated_at")
                    or entry.metadata.get("created_at")
                )
                confidence = parse_number(entry.metadata.get("confidence"), 1.0)

                if expires_at and expires_at < today and status == "active":
                    entry.metadata["status"] = "stale"
                    entry.metadata["updated_at"] = today_iso()
                    changed["stale"] += 1
                    continue

                if (
                    status == "active"
                    and confidence < 0.5
                    and last_used
                    and today - last_used >= timedelta(days=30)
                ):
                    entry.metadata["status"] = "stale"
                    entry.metadata["updated_at"] = today_iso()
                    changed["stale"] += 1
                    continue

                if (
                    status == "stale"
                    and last_used
                    and today - last_used >= timedelta(days=90)
                ):
                    entry.metadata["status"] = "archived"
                    entry.metadata["updated_at"] = today_iso()
                    changed["archived"] += 1

        normalized = {topic: [] for topic in ALL_TOPIC_FILES}
        for topic, entries in entries_by_topic.items():
            for entry in entries:
                if entry.status == "archived" and topic != "archive":
                    entry.topic = "archive"
                    normalized["archive"].append(entry)
                elif entry.status == "deprecated" and topic != "deprecated":
                    entry.topic = "deprecated"
                    normalized["deprecated"].append(entry)
                    changed["deprecated"] += 1
                else:
                    normalized[topic].append(entry)

        for topic, entries in normalized.items():
            self.write_topic_entries(user_id, topic, entries)
        self.rebuild_index(user_id)
        return changed

    def retrieve_memory_brief(
        self,
        query: str,
        user_id: str | None = None,
        limit: int = 8,
    ) -> str:
        if not self.enabled:
            return ""
        entries_by_topic = self.load_entries(user_id)
        candidates: list[tuple[int, MemoryEntry]] = []
        for topic, entries in entries_by_topic.items():
            for entry in entries:
                if entry.status not in ACTIVE_STATUSES:
                    continue
                score = self.score_entry(query, entry)
                if score > 0:
                    candidates.append((score, entry))

        candidates.sort(key=lambda item: item[0], reverse=True)
        selected = [entry for _, entry in candidates[:limit]]
        if not selected:
            return ""

        self.mark_entries_used(user_id, selected)
        lines = [
            "# Relevant Memory Brief",
            "以下是用户长期记忆中与本次问题相关的内容。若与用户最新指令冲突，以用户最新指令为准。",
            "",
        ]
        for entry in selected:
            stale_note = "（可能过期）" if entry.status == "stale" else ""
            lines.append(
                f"- [{entry.topic}#{entry.id}]{stale_note} "
                f"{self.entry_summary(entry)}"
            )
        return "\n".join(lines)

    def score_entry(self, query: str, entry: MemoryEntry) -> int:
        haystack = f"{entry.topic} {entry.kind} {entry.body}".lower()
        query_lower = query.lower()
        terms = set(re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", query_lower))
        score = 0
        if entry.status == "active":
            if entry.topic in {"user-profile", "finance-style", "workflows"}:
                score += 2
            elif entry.topic == "financial-insights":
                score += 1
        for term in terms:
            if term in haystack:
                score += 3
        if entry.status == "stale":
            score -= 2
        return score

    def mark_entries_used(
        self,
        user_id: str | None,
        selected: list[MemoryEntry],
    ) -> None:
        selected_ids = {entry.id for entry in selected}
        entries_by_topic = self.load_entries(user_id, include_special=True)
        for entries in entries_by_topic.values():
            for entry in entries:
                if entry.id in selected_ids:
                    entry.metadata["last_used_at"] = today_iso()
                    use_count = parse_int(entry.metadata.get("use_count"), 0)
                    entry.metadata["use_count"] = str(use_count + 1)
        for topic, entries in entries_by_topic.items():
            self.write_topic_entries(user_id, topic, entries)
        self.rebuild_index(user_id)

    async def run_auto_update(self, user_id: str | None = None) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "added": 0}
        self.initialize_user(user_id)
        state = self.read_state(user_id)
        last_processed_id = int(state.get("last_processed_message_id") or 0)
        messages = storage.list_messages_after(last_processed_id)
        if len(messages) < self.trigger_message_count:
            return {
                "enabled": True,
                "added": 0,
                "pending": len(messages),
                "trigger": self.trigger_message_count,
            }

        candidates = await self.extract_memory_candidates(messages)
        added = self.append_entries(user_id, candidates)
        max_message_id = max(message["id"] for message in messages)
        self.write_state(
            user_id,
            {
                "last_processed_message_id": max_message_id,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "last_added_count": added,
            },
        )
        return {
            "enabled": True,
            "added": added,
            "processed": len(messages),
            "last_processed_message_id": max_message_id,
        }

    async def extract_memory_candidates(
        self,
        messages: list[dict],
    ) -> list[MemoryEntry]:
        explicit_entries = self.extract_explicit_entries(messages)
        llm_entries = await self.extract_llm_entries(messages)
        entries = explicit_entries + llm_entries
        unique: list[MemoryEntry] = []
        seen = set()
        for entry in entries:
            key = normalize_text(f"{entry.topic}:{entry.body}")
            if key and key not in seen:
                seen.add(key)
                unique.append(entry)
        return unique

    def extract_explicit_entries(self, messages: list[dict]) -> list[MemoryEntry]:
        entries = []
        for message in messages:
            if message.get("role") != "user":
                continue
            content = str(message.get("content") or "").strip()
            if not any(marker in content for marker in EXPLICIT_MEMORY_MARKERS):
                continue
            topic, kind = self.classify_memory(content)
            entries.append(self.make_entry(topic, kind, content, confidence=0.82))
        return entries

    async def extract_llm_entries(self, messages: list[dict]) -> list[MemoryEntry]:
        message_payload = [
            {
                "role": message.get("role"),
                "content": str(message.get("content") or "")[:2000],
            }
            for message in messages
        ]
        prompt = (
            "你是金融问答产品的长期记忆整理器。请从新增对话中抽取未来有用的长期记忆。\n"
            "只抽取用户金融偏好、用户长期画像、稳定的金融研究结论、资料整理工作流。\n"
            "不要抽取账户信息、敏感信息、一次性任务、未经来源支撑的短期行情判断。\n"
            "返回 JSON 数组，每项字段：topic, kind, content, confidence, as_of_date, expires_at。\n"
            "topic 只能是 user-profile、financial-insights、finance-style、workflows。"
        )
        try:
            response = await get_llm().ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(
                        content=json.dumps(message_payload, ensure_ascii=False)
                    ),
                ]
            )
            content = str(getattr(response, "content", "") or "").strip()
            content = re.sub(r"^```(?:json)?", "", content).strip()
            content = re.sub(r"```$", "", content).strip()
            data = json.loads(content)
        except Exception:
            return []

        if not isinstance(data, list):
            return []
        entries = []
        for item in data:
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic") or "").strip()
            if topic not in TOPIC_FILES:
                topic, _ = self.classify_memory(str(item.get("content") or ""))
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            kind = str(item.get("kind") or self.default_kind(topic))
            confidence = parse_number(str(item.get("confidence", "")), 0.65)
            metadata = {}
            if item.get("as_of_date"):
                metadata["as_of_date"] = str(item["as_of_date"])
            if item.get("expires_at"):
                metadata["expires_at"] = str(item["expires_at"])
            entries.append(
                self.make_entry(
                    topic=topic,
                    kind=kind,
                    content=content,
                    confidence=confidence,
                    extra_metadata=metadata,
                )
            )
        return entries

    def classify_memory(self, content: str) -> tuple[str, str]:
        if re.search(r"财报|整理|流程|报告|watchlist|跟踪|比较|更新", content):
            return "workflows", "workflow"
        if re.search(r"风格|格式|回答|表格|结论|依据|风险提示|估值|口径", content):
            return "finance-style", "finance_style"
        if re.search(r"研究|判断|洞察|关键结论|公司|行业|财务|收入|利润|现金流", content):
            return "financial-insights", "financial_insight"
        return "user-profile", "user_profile"

    def default_kind(self, topic: str) -> str:
        return {
            "user-profile": "user_profile",
            "financial-insights": "financial_insight",
            "finance-style": "finance_style",
            "workflows": "workflow",
        }.get(topic, "note")

    def make_entry(
        self,
        topic: str,
        kind: str,
        content: str,
        confidence: float,
        extra_metadata: dict[str, str] | None = None,
    ) -> MemoryEntry:
        today = today_iso()
        metadata = {
            "status": "active",
            "source": "auto",
            "kind": kind,
            "confidence": f"{confidence:.2f}",
            "created_at": today,
            "updated_at": today,
            "last_used_at": today,
            "use_count": "0",
        }
        if topic == "financial-insights":
            metadata.setdefault("as_of_date", today)
            metadata.setdefault(
                "expires_at",
                (date.today() + timedelta(days=90)).isoformat(),
            )
        if extra_metadata:
            metadata.update(
                {key: value for key, value in extra_metadata.items() if value}
            )
        entry_id = f"mem_{now_id_stamp()}_{slugify(content)}"
        return MemoryEntry(id=entry_id, topic=topic, metadata=metadata, body=content)

    def get_index_response(self, user_id: str | None = None) -> dict[str, Any]:
        if not self.enabled:
            return {
                "enabled": False,
                "user_id": self.user_id(user_id),
                "index": "",
                "topics": [],
            }
        self.initialize_user(user_id)
        return {
            "enabled": True,
            "user_id": self.user_id(user_id),
            "index": self.index_path(user_id).read_text(encoding="utf-8"),
            "topics": list(ALL_TOPIC_FILES.values()),
        }

    def get_topic_response(self, topic_name: str, user_id: str | None = None) -> dict:
        topic = self.topic_from_name(topic_name)
        if not self.enabled:
            return {
                "enabled": False,
                "user_id": self.user_id(user_id),
                "topic": ALL_TOPIC_FILES[topic],
                "content": "",
            }
        return {
            "enabled": True,
            "user_id": self.user_id(user_id),
            "topic": ALL_TOPIC_FILES[topic],
            "content": self.read_topic(user_id, topic),
        }

    def topic_from_name(self, name: str) -> str:
        normalized = name.removesuffix(".md")
        if normalized in ALL_TOPIC_FILES:
            return normalized
        for topic, filename in ALL_TOPIC_FILES.items():
            if name == filename:
                return topic
        raise ValueError(f"Unknown memory topic: {name}")


@lru_cache(maxsize=1)
def get_memory_store() -> MemoryStore:
    return MemoryStore()


async def run_auto_memory_update(user_id: str | None = None) -> None:
    try:
        await get_memory_store().run_auto_update(user_id)
    except Exception as exc:
        print(f"auto memory update failed: {exc}")


def schedule_auto_memory_update(user_id: str | None = None) -> None:
    try:
        asyncio.create_task(run_auto_memory_update(user_id))
    except RuntimeError:
        pass
