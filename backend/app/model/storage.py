from functools import lru_cache
from typing import Optional
from uuid import uuid4

from .db import get_connection, init_database


@lru_cache(maxsize=1)
def prepare_database() -> None:
    init_database()


def create_thread(title: Optional[str] = None, thread_id: Optional[str] = None) -> dict:
    prepare_database()

    new_thread_id = thread_id or str(uuid4())
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO threads (id, title) VALUES (%s, %s)",
                (new_thread_id, title),
            )
        connection.commit()
    finally:
        connection.close()

    return get_thread(new_thread_id)


def ensure_thread(thread_id: str, title: Optional[str] = None) -> dict:
    thread = get_thread(thread_id)
    if thread:
        return thread
    return create_thread(title=title, thread_id=thread_id)


def get_thread(thread_id: str) -> Optional[dict]:
    prepare_database()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM threads WHERE id = %s", (thread_id,))
            return cursor.fetchone()
    finally:
        connection.close()


def list_threads() -> list[dict]:
    prepare_database()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM threads ORDER BY updated_at DESC")
            return cursor.fetchall()
    finally:
        connection.close()


def save_message(thread_id: str, role: str, content: str) -> dict:
    prepare_database()
    ensure_thread(thread_id)

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO messages (thread_id, role, content)
                VALUES (%s, %s, %s)
                """,
                (thread_id, role, content),
            )
            message_id = cursor.lastrowid
            cursor.execute(
                "UPDATE threads SET updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (thread_id,),
            )
        connection.commit()
    finally:
        connection.close()

    return get_message(message_id)


def get_message(message_id: int) -> Optional[dict]:
    prepare_database()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM messages WHERE id = %s", (message_id,))
            return cursor.fetchone()
    finally:
        connection.close()


def list_messages(thread_id: str) -> list[dict]:
    prepare_database()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM messages
                WHERE thread_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (thread_id,),
            )
            return cursor.fetchall()
    finally:
        connection.close()


def list_messages_after(message_id: int, limit: int = 200) -> list[dict]:
    prepare_database()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM messages
                WHERE id > %s
                ORDER BY id ASC
                LIMIT %s
                """,
                (message_id, limit),
            )
            return cursor.fetchall()
    finally:
        connection.close()


def save_file_record(
    assistant_id: str,
    original_name: str,
    saved_name: str,
    file_path: str,
    content_type: Optional[str],
    size_bytes: int,
) -> dict:
    prepare_database()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO files (
                    assistant_id,
                    original_name,
                    saved_name,
                    file_path,
                    content_type,
                    size_bytes
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    assistant_id,
                    original_name,
                    saved_name,
                    file_path,
                    content_type,
                    size_bytes,
                ),
            )
            file_id = cursor.lastrowid
        connection.commit()
    finally:
        connection.close()

    return get_file_record(file_id)


def get_file_record(file_id: int) -> Optional[dict]:
    prepare_database()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM files WHERE id = %s", (file_id,))
            return cursor.fetchone()
    finally:
        connection.close()
