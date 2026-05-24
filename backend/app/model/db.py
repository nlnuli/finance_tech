import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

from .models import CREATE_MESSAGES_TABLE, CREATE_THREADS_TABLE


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
        connection.commit()
    finally:
        connection.close()
