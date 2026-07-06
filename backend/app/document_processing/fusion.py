from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import BoundingBox, NormalizedDocument, TextBlock, UnifiedDocument


FUSION_VERSION = "1.0"


def _area(box: BoundingBox) -> float:
    return max(0.0, box.right - box.left) * max(0.0, box.bottom - box.top)


def _intersection_area(left: BoundingBox, right: BoundingBox) -> float:
    width = max(0.0, min(left.right, right.right) - max(left.left, right.left))
    height = max(0.0, min(left.bottom, right.bottom) - max(left.top, right.top))
    return width * height


def bounding_box_iou(left: BoundingBox, right: BoundingBox) -> float:
    intersection = _intersection_area(left, right)
    union = _area(left) + _area(right) - intersection
    return intersection / union if union else 0.0


def bounding_box_overlap_ratio(inner: BoundingBox, outer: BoundingBox) -> float:
    area = _area(inner)
    return _intersection_area(inner, outer) / area if area else 0.0


def normalize_comparison_text(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value).lower()


def text_similarity(left: str, right: str) -> float:
    normalized_left = normalize_comparison_text(left)
    normalized_right = normalize_comparison_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def _inside_table(block: TextBlock, tables) -> str | None:
    for table in tables:
        if table.page_number != block.page_number:
            continue
        if bounding_box_overlap_ratio(block.bounding_box, table.bounding_box) >= 0.7:
            return table.id
    return None


def _infer_table_titles(tables, blocks: list[TextBlock]) -> None:
    for table in tables:
        candidates = [
            block
            for block in blocks
            if block.page_number == table.page_number
            and not block.consumed_by
            and block.bounding_box.bottom <= table.bounding_box.top
            and table.bounding_box.top - block.bounding_box.bottom <= 0.12
            and len(block.text.strip()) <= 120
        ]
        if candidates:
            table.title = max(candidates, key=lambda block: block.bounding_box.bottom).text


def fuse_documents(
    file_id: int,
    filename: str,
    ocr: NormalizedDocument,
    form: NormalizedDocument,
) -> UnifiedDocument:
    blocks = [block.model_copy(deep=True) for block in ocr.blocks]
    tables = [table.model_copy(deep=True) for table in form.tables]
    fields = [field.model_copy(deep=True) for field in form.fields]
    warnings: list[str] = []

    for block in blocks:
        table_id = _inside_table(block, tables)
        if table_id:
            block.consumed_by = table_id

    for form_block in form.blocks:
        if _inside_table(form_block, tables):
            continue

        candidates = [
            block
            for block in blocks
            if block.page_number == form_block.page_number
            and bounding_box_iou(block.bounding_box, form_block.bounding_box) >= 0.6
        ]
        match = next(
            (
                block
                for block in sorted(
                    candidates,
                    key=lambda item: bounding_box_iou(
                        item.bounding_box, form_block.bounding_box
                    ),
                    reverse=True,
                )
                if text_similarity(block.text, form_block.text) >= 0.9
            ),
            None,
        )
        if match:
            match.confidence = max(match.confidence, form_block.confidence)
            for source in form_block.source_processors:
                if source not in match.source_processors:
                    match.source_processors.append(source)
            for source_ref in form_block.source_refs:
                if source_ref not in match.source_refs:
                    match.source_refs.append(source_ref)
            continue

        retained = form_block.model_copy(deep=True)
        retained.reading_order = max(
            [
                block.reading_order
                for block in blocks
                if block.page_number == retained.page_number
            ]
            or [0]
        ) + 1
        blocks.append(retained)
        warnings.append(
            f"retained unmatched form text block {form_block.id} "
            f"on page {form_block.page_number}"
        )

    blocks.sort(
        key=lambda block: (
            block.page_number,
            block.bounding_box.top,
            block.bounding_box.left,
            block.reading_order,
        )
    )
    _infer_table_titles(tables, blocks)

    page_by_number = {page.page_number: page for page in ocr.pages}
    for page in form.pages:
        page_by_number.setdefault(page.page_number, page)

    return UnifiedDocument(
        schema_version=FUSION_VERSION,
        file_id=file_id,
        filename=filename,
        page_count=max(ocr.page_count, form.page_count),
        pages=[page_by_number[number] for number in sorted(page_by_number)],
        blocks=blocks,
        tables=tables,
        fields=fields,
        processors={
            "ocr": ocr.processor_id,
            "form": form.processor_id,
        },
        fusion_warnings=warnings,
    )
