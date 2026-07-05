from functools import lru_cache
from typing import Optional
from uuid import uuid4

from ..security import hash_password, normalize_email
from .db import get_connection, init_database


@lru_cache(maxsize=1)
def prepare_database() -> None:
    init_database()


def create_user(email: str, password: str, display_name: Optional[str] = None) -> dict:
    prepare_database()
    user_id = str(uuid4())
    normalized_email = normalize_email(email)
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (id, email, display_name, password_hash)
                VALUES (%s, %s, %s, %s)
                """,
                (user_id, normalized_email, display_name, hash_password(password)),
            )
        connection.commit()
    finally:
        connection.close()
    return get_user(user_id)


def get_user(user_id: str) -> Optional[dict]:
    prepare_database()
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, display_name, password_hash, created_at, updated_at
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            return cursor.fetchone()
    finally:
        connection.close()


def get_user_by_email(email: str) -> Optional[dict]:
    prepare_database()
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, display_name, password_hash, created_at, updated_at
                FROM users
                WHERE email = %s
                """,
                (normalize_email(email),),
            )
            return cursor.fetchone()
    finally:
        connection.close()


def create_thread(
    user_id: str,
    title: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> dict:
    prepare_database()

    new_thread_id = thread_id or str(uuid4())
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO threads (id, user_id, title) VALUES (%s, %s, %s)",
                (new_thread_id, user_id, title),
            )
        connection.commit()
    finally:
        connection.close()

    return get_thread(user_id, new_thread_id)


def ensure_thread(user_id: str, thread_id: str, title: Optional[str] = None) -> dict:
    thread = get_thread(user_id, thread_id)
    if thread:
        return thread
    return create_thread(user_id, title=title, thread_id=thread_id)


def get_thread(user_id: str, thread_id: str) -> Optional[dict]:
    prepare_database()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM threads WHERE id = %s AND user_id = %s",
                (thread_id, user_id),
            )
            return cursor.fetchone()
    finally:
        connection.close()


def list_threads(user_id: str) -> list[dict]:
    prepare_database()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM threads
                WHERE user_id = %s
                ORDER BY updated_at DESC
                """,
                (user_id,),
            )
            return cursor.fetchall()
    finally:
        connection.close()


def save_message(user_id: str, thread_id: str, role: str, content: str) -> dict:
    prepare_database()
    ensure_thread(user_id, thread_id)

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
                """
                UPDATE threads
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s
                """,
                (thread_id, user_id),
            )
        connection.commit()
    finally:
        connection.close()

    return get_message(user_id, message_id)


def get_message(user_id: str, message_id: int) -> Optional[dict]:
    prepare_database()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT messages.*
                FROM messages
                JOIN threads ON threads.id = messages.thread_id
                WHERE messages.id = %s AND threads.user_id = %s
                """,
                (message_id, user_id),
            )
            return cursor.fetchone()
    finally:
        connection.close()


def list_messages(user_id: str, thread_id: str) -> list[dict]:
    prepare_database()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT messages.*
                FROM messages
                JOIN threads ON threads.id = messages.thread_id
                WHERE messages.thread_id = %s AND threads.user_id = %s
                ORDER BY messages.created_at ASC, messages.id ASC
                """,
                (thread_id, user_id),
            )
            return cursor.fetchall()
    finally:
        connection.close()


def list_messages_after(
    message_id: int,
    limit: int = 200,
    user_id: str | None = None,
) -> list[dict]:
    prepare_database()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            if user_id:
                cursor.execute(
                    """
                    SELECT messages.*
                    FROM messages
                    JOIN threads ON threads.id = messages.thread_id
                    WHERE messages.id > %s AND threads.user_id = %s
                    ORDER BY messages.id ASC
                    LIMIT %s
                    """,
                    (message_id, user_id, limit),
                )
            else:
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
    user_id: str,
    assistant_id: str,
    original_name: str,
    saved_name: str,
    file_path: str,
    content_type: Optional[str],
    size_bytes: int,
    status: str = "ready",
) -> dict:
    prepare_database()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO files (
                    assistant_id,
                    user_id,
                    original_name,
                    saved_name,
                    file_path,
                    content_type,
                    size_bytes,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    assistant_id,
                    user_id,
                    original_name,
                    saved_name,
                    file_path,
                    content_type,
                    size_bytes,
                    status,
                ),
            )
            file_id = cursor.lastrowid
        connection.commit()
    finally:
        connection.close()

    return get_file_record(file_id, user_id=user_id)


def update_file_processing(
    file_id: int,
    status: str,
    page_count: int | None = None,
    chunk_count: int | None = None,
    artifact_dir: str | None = None,
    processing_error: str | None = None,
) -> dict:
    prepare_database()
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE files
                SET status = %s,
                    page_count = COALESCE(%s, page_count),
                    chunk_count = COALESCE(%s, chunk_count),
                    artifact_dir = COALESCE(%s, artifact_dir),
                    processing_error = %s
                WHERE id = %s
                """,
                (
                    status,
                    page_count,
                    chunk_count,
                    artifact_dir,
                    processing_error,
                    file_id,
                ),
            )
        connection.commit()
    finally:
        connection.close()
    return get_file_record(file_id)


def get_file_record(file_id: int, user_id: str | None = None) -> Optional[dict]:
    prepare_database()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            if user_id:
                cursor.execute(
                    "SELECT * FROM files WHERE id = %s AND user_id = %s",
                    (file_id, user_id),
                )
            else:
                cursor.execute("SELECT * FROM files WHERE id = %s", (file_id,))
            return cursor.fetchone()
    finally:
        connection.close()


def list_file_records(
    user_id: str | None = None,
    assistant_id: str | None = None,
    statuses: tuple[str, ...] = ("ready",),
    after_file_id: int | None = None,
) -> list[dict]:
    prepare_database()
    conditions = []
    parameters: list[object] = []

    if user_id:
        conditions.append("user_id = %s")
        parameters.append(user_id)
    if assistant_id:
        conditions.append("assistant_id = %s")
        parameters.append(assistant_id)
    if statuses:
        placeholders = ", ".join(["%s"] * len(statuses))
        conditions.append(f"status IN ({placeholders})")
        parameters.extend(statuses)
    if after_file_id is not None:
        conditions.append("id > %s")
        parameters.append(after_file_id)

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM files{where_clause} ORDER BY id ASC",
                tuple(parameters),
            )
            return cursor.fetchall()
    finally:
        connection.close()
