import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

from .models import (
    CREATE_FILES_TABLE,
    CREATE_MESSAGES_TABLE,
    CREATE_THREADS_TABLE,
    FILE_COLUMN_MIGRATIONS,
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
            cursor.execute(CREATE_THREADS_TABLE)
            cursor.execute(CREATE_MESSAGES_TABLE)
            cursor.execute(CREATE_FILES_TABLE)
            cursor.execute(
                """
                SELECT COLUMN_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'files'
                """,
                (database_name,),
            )
            existing_columns = {row["COLUMN_NAME"] for row in cursor.fetchall()}
            for column_name, definition in FILE_COLUMN_MIGRATIONS.items():
                if column_name not in existing_columns:
                    cursor.execute(f"ALTER TABLE files ADD COLUMN {definition}")
        connection.commit()
    finally:
        connection.close()
