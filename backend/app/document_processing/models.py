from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ProcessorKind = Literal["ocr", "form"]


class BoundingBox(BaseModel):
    left: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0


class PageInfo(BaseModel):
    page_number: int
    width: float = 0.0
    height: float = 0.0


class TextBlock(BaseModel):
    id: str
    page_number: int
    text: str
    bounding_box: BoundingBox = Field(default_factory=BoundingBox)
    confidence: float = 0.0
    reading_order: int = 0
    source_processors: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    consumed_by: str | None = None


class TableCell(BaseModel):
    text: str
    row_index: int
    column_index: int
    row_span: int = 1
    column_span: int = 1
    bounding_box: BoundingBox = Field(default_factory=BoundingBox)
    confidence: float = 0.0


class TableRow(BaseModel):
    cells: list[TableCell] = Field(default_factory=list)
    source_page_number: int | None = None
    source_table_id: str | None = None


class DocumentTable(BaseModel):
    id: str
    page_number: int
    title: str | None = None
    header_rows: list[TableRow] = Field(default_factory=list)
    body_rows: list[TableRow] = Field(default_factory=list)
    bounding_box: BoundingBox = Field(default_factory=BoundingBox)
    confidence: float = 0.0
    source_processors: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class TableSegmentRef(BaseModel):
    table_id: str
    page_number: int
    bounding_box: BoundingBox = Field(default_factory=BoundingBox)


class LogicalTable(BaseModel):
    id: str
    title: str | None = None
    page_start: int
    page_end: int
    header_rows: list[TableRow] = Field(default_factory=list)
    body_rows: list[TableRow] = Field(default_factory=list)
    segments: list[TableSegmentRef] = Field(default_factory=list)
    source_table_ids: list[str] = Field(default_factory=list)
    stitch_confidence: float = 1.0
    source_processors: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class TableStitchDecision(BaseModel):
    previous_table_id: str
    next_table_id: str
    score: float
    matched: bool = False
    feature_scores: dict[str, float] = Field(default_factory=dict)
    rejection_reasons: list[str] = Field(default_factory=list)


class TableStitchingResult(BaseModel):
    version: str = "1.0"
    logical_tables: list[LogicalTable] = Field(default_factory=list)
    decisions: list[TableStitchDecision] = Field(default_factory=list)
    physical_table_count: int = 0
    logical_table_count: int = 0
    stitched_table_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class FormField(BaseModel):
    id: str
    page_number: int
    key: str
    value: str
    value_type: str = ""
    key_bounding_box: BoundingBox = Field(default_factory=BoundingBox)
    value_bounding_box: BoundingBox = Field(default_factory=BoundingBox)
    confidence: float = 0.0
    source_processors: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class NormalizedDocument(BaseModel):
    processor_kind: ProcessorKind
    processor_id: str
    processor_version: str = ""
    complete: bool = True
    page_count: int = 0
    batch_count: int = 0
    pages: list[PageInfo] = Field(default_factory=list)
    blocks: list[TextBlock] = Field(default_factory=list)
    tables: list[DocumentTable] = Field(default_factory=list)
    fields: list[FormField] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class UnifiedDocument(BaseModel):
    schema_version: str = "1.0"
    file_id: int
    filename: str
    page_count: int
    pages: list[PageInfo] = Field(default_factory=list)
    blocks: list[TextBlock] = Field(default_factory=list)
    tables: list[DocumentTable] = Field(default_factory=list)
    fields: list[FormField] = Field(default_factory=list)
    processors: dict[str, str] = Field(default_factory=dict)
    fusion_warnings: list[str] = Field(default_factory=list)
