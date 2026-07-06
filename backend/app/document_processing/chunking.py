from __future__ import annotations

from collections import defaultdict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .models import DocumentTable, FormField, LogicalTable, TableRow, UnifiedDocument


def _base_metadata(
    filename: str,
    assistant_id: str,
    user_id: str,
    file_id: int,
    content_type: str,
    page_start: int,
    page_end: int,
) -> dict:
    return {
        "filename": filename,
        "assistant_id": assistant_id,
        "user_id": user_id,
        "file_id": file_id,
        "content_type": content_type,
        "page_start": page_start,
        "page_end": page_end,
        "fusion_version": "1.0",
    }


def _row_values(row: TableRow) -> list[str]:
    return [
        cell.text.strip()
        for cell in sorted(row.cells, key=lambda cell: cell.column_index)
    ]


def _escape_markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


TableLike = DocumentTable | LogicalTable


def _table_page_range(table: TableLike) -> tuple[int, int]:
    if isinstance(table, LogicalTable):
        return table.page_start, table.page_end
    return table.page_number, table.page_number


def _table_headers(table: TableLike) -> list[str]:
    header_rows = [_row_values(row) for row in table.header_rows]
    column_count = max(
        [len(row) for row in header_rows]
        + [len(_row_values(row)) for row in table.body_rows]
        + [1]
    )
    if not header_rows:
        return [f"列{index + 1}" for index in range(column_count)]

    headers = []
    for column_index in range(column_count):
        values = [
            row[column_index]
            for row in header_rows
            if column_index < len(row) and row[column_index]
        ]
        headers.append(" / ".join(values) or f"列{column_index + 1}")
    return headers


def _render_table_markdown(
    table: TableLike,
    headers: list[str],
    rows: list[list[str]],
) -> str:
    title = table.title or table.id
    page_start, page_end = _table_page_range(table)
    page_value = (
        str(page_start) if page_start == page_end else f"{page_start}-{page_end}"
    )
    lines = [f"表格：{title}", f"页码：{page_value}", ""]
    lines.append(
        "| " + " | ".join(_escape_markdown_cell(value) for value in headers) + " |"
    )
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        padded = row + [""] * (len(headers) - len(row))
        lines.append(
            "| "
            + " | ".join(
                _escape_markdown_cell(value) for value in padded[: len(headers)]
            )
            + " |"
        )
    return "\n".join(lines)


def _text_chunks(
    document: UnifiedDocument,
    assistant_id: str,
    user_id: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict]:
    effective_overlap = min(chunk_overlap, max(0, chunk_size - 1))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=effective_overlap,
    )
    blocks_by_page = defaultdict(list)
    for block in document.blocks:
        if not block.consumed_by and block.text.strip():
            blocks_by_page[block.page_number].append(block)

    chunks = []
    for page_number in sorted(blocks_by_page):
        blocks = blocks_by_page[page_number]
        text = "\n\n".join(block.text.strip() for block in blocks)
        for part_index, chunk_text in enumerate(splitter.split_text(text)):
            metadata = _base_metadata(
                document.filename,
                assistant_id,
                user_id,
                document.file_id,
                "text",
                page_number,
                page_number,
            )
            metadata.update(
                {
                    "source_id": f"page-{page_number}",
                    "part_index": part_index,
                    "source_block_ids": [block.id for block in blocks],
                    "processor_sources": sorted(
                        {
                            source
                            for block in blocks
                            for source in block.source_processors
                        }
                    ),
                }
            )
            chunks.append({"content": chunk_text, "metadata": metadata})
    return chunks


def _table_chunks(
    document: UnifiedDocument,
    assistant_id: str,
    user_id: str,
    chunk_size: int,
    logical_tables: list[LogicalTable] | None = None,
) -> list[dict]:
    chunks = []
    tables: list[TableLike] = (
        logical_tables if logical_tables is not None else document.tables
    )
    for table in tables:
        headers = _table_headers(table)
        row_groups: list[tuple[int, list[TableRow]]] = []
        current_rows: list[TableRow] = []
        current_start = 0

        for row_index, row in enumerate(table.body_rows):
            candidate = current_rows + [row]
            rendered_candidate = [_row_values(item) for item in candidate]
            if (
                current_rows
                and len(_render_table_markdown(table, headers, rendered_candidate))
                > chunk_size
            ):
                row_groups.append((current_start, current_rows))
                current_rows = [row]
                current_start = row_index
            else:
                current_rows = candidate
        if current_rows or not table.body_rows:
            row_groups.append((current_start, current_rows))

        for part_index, (row_start, rows) in enumerate(row_groups):
            rendered_rows = [_row_values(row) for row in rows]
            page_start, page_end = _table_page_range(table)
            source_table_ids = getattr(table, "source_table_ids", [table.id])
            row_source_pages = sorted(
                {row.source_page_number or page_start for row in rows}
            )
            content = _render_table_markdown(table, headers, rendered_rows)
            metadata = _base_metadata(
                document.filename,
                assistant_id,
                user_id,
                document.file_id,
                "table",
                page_start,
                page_end,
            )
            metadata.update(
                {
                    "source_id": table.id,
                    "part_index": part_index,
                    "table_id": table.id,
                    "row_start": row_start,
                    "row_end": row_start + max(len(rows) - 1, 0),
                    "processor_sources": table.source_processors,
                    "logical_table_id": table.id,
                    "source_table_ids": source_table_ids,
                    "is_cross_page": page_start != page_end,
                    "stitch_confidence": getattr(
                        table,
                        "stitch_confidence",
                        1.0,
                    ),
                    "row_source_pages": row_source_pages,
                    "structured_data": {
                        "title": table.title,
                        "headers": headers,
                        "rows": rendered_rows,
                        "row_source_pages": [
                            row.source_page_number or page_start for row in rows
                        ],
                    },
                }
            )
            chunks.append({"content": content, "metadata": metadata})
    return chunks


def _form_field_chunks(
    document: UnifiedDocument,
    assistant_id: str,
    user_id: str,
    chunk_size: int,
) -> list[dict]:
    fields_by_page: dict[int, list[FormField]] = defaultdict(list)
    for field in document.fields:
        fields_by_page[field.page_number].append(field)

    chunks = []
    for page_number in sorted(fields_by_page):
        groups: list[list[FormField]] = []
        current: list[FormField] = []
        for field in fields_by_page[page_number]:
            candidate = current + [field]
            candidate_text = "\n".join(
                f"{item.key or '字段'}：{item.value}" for item in candidate
            )
            if current and len(candidate_text) > chunk_size:
                groups.append(current)
                current = [field]
            else:
                current = candidate
        if current:
            groups.append(current)

        for part_index, group in enumerate(groups):
            content = "\n".join(
                f"{field.key or '字段'}：{field.value}" for field in group
            )
            metadata = _base_metadata(
                document.filename,
                assistant_id,
                user_id,
                document.file_id,
                "form_field",
                page_number,
                page_number,
            )
            metadata.update(
                {
                    "source_id": f"form-page-{page_number}",
                    "part_index": part_index,
                    "source_block_ids": [field.id for field in group],
                    "processor_sources": sorted(
                        {
                            source
                            for field in group
                            for source in field.source_processors
                        }
                    ),
                    "structured_data": [
                        {
                            "key": field.key,
                            "value": field.value,
                            "value_type": field.value_type,
                        }
                        for field in group
                    ],
                }
            )
            chunks.append({"content": content, "metadata": metadata})
    return chunks


def build_document_chunks(
    document: UnifiedDocument,
    assistant_id: str,
    user_id: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    logical_tables: list[LogicalTable] | None = None,
) -> list[dict]:
    chunks = [
        *_text_chunks(document, assistant_id, user_id, chunk_size, chunk_overlap),
        *_table_chunks(document, assistant_id, user_id, chunk_size, logical_tables),
        *_form_field_chunks(document, assistant_id, user_id, chunk_size),
    ]
    for chunk_index, chunk in enumerate(chunks):
        metadata = chunk["metadata"]
        metadata["chunk_index"] = chunk_index
        metadata["chunk_id"] = (
            f"file-{document.file_id}-{metadata['content_type']}-"
            f"{metadata['source_id']}-{metadata['part_index']}"
        )
    return chunks
