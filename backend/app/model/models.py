CREATE_THREADS_TABLE = """
CREATE TABLE IF NOT EXISTS threads (
    id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
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
    INDEX idx_files_assistant_id (assistant_id)
)
"""


FILE_COLUMN_MIGRATIONS = {
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
