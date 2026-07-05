CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(64) PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    password_hash VARCHAR(500) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX idx_users_email (email)
)
"""


CREATE_THREADS_TABLE = """
CREATE TABLE IF NOT EXISTS threads (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    title VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_threads_user_id (user_id)
)
"""


CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS messages (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    thread_id VARCHAR(64) NOT NULL,
    role VARCHAR(32) NOT NULL,
    content LONGTEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_messages_thread_id (thread_id),
    CONSTRAINT fk_messages_thread_id
        FOREIGN KEY (thread_id) REFERENCES threads(id)
        ON DELETE CASCADE
)
"""


CREATE_FILES_TABLE = """
CREATE TABLE IF NOT EXISTS files (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id VARCHAR(64) NOT NULL,
    assistant_id VARCHAR(64) NOT NULL,
    original_name VARCHAR(255) NOT NULL,
    saved_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    content_type VARCHAR(100),
    size_bytes BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'ready',
    page_count INT,
    chunk_count INT NOT NULL DEFAULT 0,
    artifact_dir VARCHAR(500),
    processing_error LONGTEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_files_user_id (user_id),
    INDEX idx_files_assistant_id (assistant_id)
)
"""


THREAD_COLUMN_MIGRATIONS = {
    "user_id": "user_id VARCHAR(64)",
}


FILE_COLUMN_MIGRATIONS = {
    "user_id": "user_id VARCHAR(64)",
    "status": "status VARCHAR(32) NOT NULL DEFAULT 'ready'",
    "page_count": "page_count INT",
    "chunk_count": "chunk_count INT NOT NULL DEFAULT 0",
    "artifact_dir": "artifact_dir VARCHAR(500)",
    "processing_error": "processing_error LONGTEXT",
    "updated_at": (
        "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP "
        "ON UPDATE CURRENT_TIMESTAMP"
    ),
}


TABLE_INDEX_MIGRATIONS = {
    "threads": {
        "idx_threads_user_id": "CREATE INDEX idx_threads_user_id ON threads (user_id)",
    },
    "files": {
        "idx_files_user_id": "CREATE INDEX idx_files_user_id ON files (user_id)",
    },
}
