import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

from ..config import get_settings
from ..security import hash_password, normalize_email
from .models import (
    CREATE_FILES_TABLE,
    CREATE_MESSAGES_TABLE,
    CREATE_THREADS_TABLE,
    CREATE_USERS_TABLE,
    FILE_COLUMN_MIGRATIONS,
    TABLE_INDEX_MIGRATIONS,
    THREAD_COLUMN_MIGRATIONS,
)


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ENV_FILE)


def get_database_name() -> str:
    return os.getenv("MYSQL_DATABASE", "finance_tech")


def get_mysql_config(include_database: bool = True) -> dict:
    config = {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
    }

    if include_database:
        config["database"] = get_database_name()

    return config


def get_connection():
    return pymysql.connect(**get_mysql_config())


DEFAULT_USER_ID = "default"
DISABLED_PASSWORD_HASH = "disabled"


def _table_columns(cursor, database_name: str, table_name: str) -> set[str]:
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        """,
        (database_name, table_name),
    )
    return {row["COLUMN_NAME"] for row in cursor.fetchall()}


def _table_indexes(cursor, database_name: str, table_name: str) -> set[str]:
    cursor.execute(
        """
        SELECT INDEX_NAME
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        """,
        (database_name, table_name),
    )
    return {row["INDEX_NAME"] for row in cursor.fetchall()}


def _legacy_owned_row_count(cursor) -> int:
    total = 0
    for table_name in ("threads", "files"):
        cursor.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM {table_name}
            WHERE user_id IS NULL OR user_id = ''
            """
        )
        total += int(cursor.fetchone()["count"])
    return total


def _ensure_default_user(cursor) -> None:
    settings = get_settings()
    email = normalize_email(settings.default_user_email)
    password_hash = (
        hash_password(settings.default_user_password)
        if settings.default_user_password
        else DISABLED_PASSWORD_HASH
    )
    cursor.execute(
        """
        INSERT INTO users (id, email, display_name, password_hash)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            email = VALUES(email),
            display_name = COALESCE(users.display_name, VALUES(display_name)),
            password_hash = IF(users.password_hash = %s, VALUES(password_hash), users.password_hash)
        """,
        (
            DEFAULT_USER_ID,
            email,
            "Default User",
            password_hash,
            DISABLED_PASSWORD_HASH,
        ),
    )


def init_database() -> None:
    database_name = get_database_name()

    connection = pymysql.connect(**get_mysql_config(include_database=False))
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cursor.execute(f"USE `{database_name}`")
            cursor.execute(CREATE_USERS_TABLE)
            cursor.execute(CREATE_THREADS_TABLE)
            cursor.execute(CREATE_MESSAGES_TABLE)
            cursor.execute(CREATE_FILES_TABLE)

            existing_columns = _table_columns(cursor, database_name, "threads")
            for column_name, definition in THREAD_COLUMN_MIGRATIONS.items():
                if column_name not in existing_columns:
                    cursor.execute(f"ALTER TABLE threads ADD COLUMN {definition}")

            existing_columns = _table_columns(cursor, database_name, "files")
            for column_name, definition in FILE_COLUMN_MIGRATIONS.items():
                if column_name not in existing_columns:
                    cursor.execute(f"ALTER TABLE files ADD COLUMN {definition}")

            _ensure_default_user(cursor)
            legacy_count = _legacy_owned_row_count(cursor)
            settings = get_settings()
            if (
                legacy_count
                and settings.app_env != "development"
                and not settings.default_user_password
            ):
                raise RuntimeError(
                    "DEFAULT_USER_PASSWORD must be set when migrating existing "
                    "data outside development."
                )
            cursor.execute(
                "UPDATE threads SET user_id = %s WHERE user_id IS NULL OR user_id = ''",
                (DEFAULT_USER_ID,),
            )
            cursor.execute(
                "UPDATE files SET user_id = %s WHERE user_id IS NULL OR user_id = ''",
                (DEFAULT_USER_ID,),
            )

            for table_name, index_definitions in TABLE_INDEX_MIGRATIONS.items():
                existing_indexes = _table_indexes(cursor, database_name, table_name)
                for index_name, statement in index_definitions.items():
                    if index_name not in existing_indexes:
                        cursor.execute(statement)
        connection.commit()
    finally:
        connection.close()
