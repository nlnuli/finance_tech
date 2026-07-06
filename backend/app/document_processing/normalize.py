from __future__ import annotations

from collections.abc import Iterable

from .models import (
    BoundingBox,
    DocumentTable,
    FormField,
    NormalizedDocument,
    PageInfo,
    TableCell,
    TableRow,
    TextBlock,
)


def _items(value: object, attribute: str) -> list:
    return list(getattr(value, attribute, None) or [])


def get_document_processor_version(document: object) -> str:
    revisions = _items(document, "revisions")
    for revision in reversed(revisions):
        processor = str(getattr(revision, "processor", "") or "")
        if processor:
            return processor
    return "default"


def text_from_layout(document_text: str, layout: object | None) -> str:
    if layout is None:
        return ""
    anchor = getattr(layout, "text_anchor", None)
    segments = getattr(anchor, "text_segments", None) or []
    parts = []
    for segment in segments:
        start = int(getattr(segment, "start_index", 0) or 0)
        end = int(getattr(segment, "end_index", 0) or 0)
        if end > start:
            parts.append(document_text[start:end])
    return "".join(parts).strip()


def _vertex_xy(vertex: object) -> tuple[float, float]:
    return (
        float(getattr(vertex, "x", 0.0) or 0.0),
        float(getattr(vertex, "y", 0.0) or 0.0),
    )


def bounding_box_from_layout(
    layout: object | None,
    page_width: float,
    page_height: float,
) -> BoundingBox:
    if layout is None:
        return BoundingBox()
    poly = getattr(layout, "bounding_poly", None)
    normalized = list(getattr(poly, "normalized_vertices", None) or [])
    vertices = normalized or list(getattr(poly, "vertices", None) or [])
    if not vertices:
        return BoundingBox()

    coordinates = [_vertex_xy(vertex) for vertex in vertices]
    if not normalized:
        width = page_width or 1.0
        height = page_height or 1.0
        coordinates = [(x / width, y / height) for x, y in coordinates]

    xs = [min(1.0, max(0.0, value[0])) for value in coordinates]
    ys = [min(1.0, max(0.0, value[1])) for value in coordinates]
    return BoundingBox(left=min(xs), top=min(ys), right=max(xs), bottom=max(ys))


def _layout_confidence(layout: object | None) -> float:
    return float(getattr(layout, "confidence", 0.0) or 0.0)


def _normalize_rows(
    rows: Iterable,
    document_text: str,
    page_width: float,
    page_height: float,
    start_row_index: int,
) -> list[TableRow]:
    normalized_rows = []
    for row_offset, row in enumerate(rows):
        cells = []
        for column_index, cell in enumerate(_items(row, "cells")):
            layout = getattr(cell, "layout", None)
            cells.append(
                TableCell(
                    text=text_from_layout(document_text, layout),
                    row_index=start_row_index + row_offset,
                    column_index=column_index,
                    row_span=int(getattr(cell, "row_span", 1) or 1),
                    column_span=int(getattr(cell, "col_span", 1) or 1),
                    bounding_box=bounding_box_from_layout(
                        layout, page_width, page_height
                    ),
                    confidence=_layout_confidence(layout),
                )
            )
        normalized_rows.append(TableRow(cells=cells))
    return normalized_rows


def normalize_document(
    document: object,
    processor_kind: str,
    processor_id: str,
    page_offset: int = 0,
    processor_version: str = "",
) -> NormalizedDocument:
    document_text = str(getattr(document, "text", "") or "")
    pages = []
    blocks = []
    tables = []
    fields = []

    for local_page_index, page in enumerate(_items(document, "pages"), start=1):
        page_number = page_offset + local_page_index
        dimension = getattr(page, "dimension", None)
        page_width = float(getattr(dimension, "width", 0.0) or 0.0)
        page_height = float(getattr(dimension, "height", 0.0) or 0.0)
        pages.append(
            PageInfo(
                page_number=page_number,
                width=page_width,
                height=page_height,
            )
        )

        page_blocks = _items(page, "blocks") or _items(page, "paragraphs")
        for reading_order, block in enumerate(page_blocks):
            layout = getattr(block, "layout", None)
            text = text_from_layout(document_text, layout)
            if not text:
                continue
            block_id = f"{processor_kind}_p{page_number}_b{reading_order}"
            blocks.append(
                TextBlock(
                    id=block_id,
                    page_number=page_number,
                    text=text,
                    bounding_box=bounding_box_from_layout(
                        layout, page_width, page_height
                    ),
                    confidence=_layout_confidence(layout),
                    reading_order=reading_order,
                    source_processors=[processor_kind],
                    source_refs=[block_id],
                )
            )

        for table_index, table in enumerate(_items(page, "tables")):
            table_id = f"{processor_kind}_p{page_number}_t{table_index}"
            header_source = _items(table, "header_rows")
            body_source = _items(table, "body_rows")
            header_rows = _normalize_rows(
                header_source,
                document_text,
                page_width,
                page_height,
                start_row_index=0,
            )
            body_rows = _normalize_rows(
                body_source,
                document_text,
                page_width,
                page_height,
                start_row_index=len(header_rows),
            )
            layout = getattr(table, "layout", None)
            tables.append(
                DocumentTable(
                    id=table_id,
                    page_number=page_number,
                    header_rows=header_rows,
                    body_rows=body_rows,
                    bounding_box=bounding_box_from_layout(
                        layout, page_width, page_height
                    ),
                    confidence=_layout_confidence(layout),
                    source_processors=[processor_kind],
                    source_refs=[table_id],
                )
            )

        for field_index, form_field in enumerate(_items(page, "form_fields")):
            field_id = f"{processor_kind}_p{page_number}_f{field_index}"
            name_layout = getattr(form_field, "field_name", None)
            value_layout = getattr(form_field, "field_value", None)
            key = text_from_layout(document_text, name_layout)
            value = text_from_layout(document_text, value_layout)
            if not key and not value:
                continue
            fields.append(
                FormField(
                    id=field_id,
                    page_number=page_number,
                    key=key,
                    value=value,
                    value_type=str(getattr(form_field, "value_type", "") or ""),
                    key_bounding_box=bounding_box_from_layout(
                        name_layout, page_width, page_height
                    ),
                    value_bounding_box=bounding_box_from_layout(
                        value_layout, page_width, page_height
                    ),
                    confidence=max(
                        _layout_confidence(name_layout),
                        _layout_confidence(value_layout),
                    ),
                    source_processors=[processor_kind],
                    source_refs=[field_id],
                )
            )

    return NormalizedDocument(
        processor_kind=processor_kind,
        processor_id=processor_id,
        processor_version=processor_version,
        page_count=len(pages),
        batch_count=1,
        pages=pages,
        blocks=blocks,
        tables=tables,
        fields=fields,
    )


def merge_normalized_documents(
    documents: list[NormalizedDocument],
    processor_kind: str,
    processor_id: str,
    errors: list[str] | None = None,
) -> NormalizedDocument:
    pages = [page for document in documents for page in document.pages]
    blocks = [block for document in documents for block in document.blocks]
    tables = [table for document in documents for table in document.tables]
    fields = [field for document in documents for field in document.fields]
    return NormalizedDocument(
        processor_kind=processor_kind,
        processor_id=processor_id,
        processor_version=next(
            (document.processor_version for document in documents if document.processor_version),
            "",
        ),
        complete=not errors,
        page_count=len({page.page_number for page in pages}),
        batch_count=len(documents),
        pages=sorted(pages, key=lambda page: page.page_number),
        blocks=sorted(
            blocks, key=lambda block: (block.page_number, block.reading_order)
        ),
        tables=sorted(tables, key=lambda table: (table.page_number, table.bounding_box.top)),
        fields=sorted(fields, key=lambda field: (field.page_number, field.key_bounding_box.top)),
        errors=errors or [],
    )
