from __future__ import annotations

import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from statistics import median
from uuid import NAMESPACE_URL, uuid5

from .models import (
    DocumentTable,
    LogicalTable,
    TableRow,
    TableSegmentRef,
    TableStitchDecision,
    TableStitchingResult,
    TextBlock,
)

BOTTOM_EDGE_MIN = 0.70
TOP_EDGE_MAX = 0.30
STRONG_SIGNAL_MIN = 0.75
REPEATED_HEADER_MIN = 0.90
REPEATED_BOUNDARY_ROW_MIN = 0.95

FEATURE_WEIGHTS = {
    "column_geometry": 0.25,
    "header": 0.20,
    "context": 0.20,
    "column_types": 0.15,
    "edge_position": 0.10,
    "financial_semantics": 0.10,
}

STATEMENT_KEYWORDS = {
    "cash_flow": (
        "cash flows",
        "operating activities",
        "investing activities",
        "financing activities",
        "cash equivalents",
    ),
    "balance_sheet": (
        "balance sheets",
        "current assets",
        "non-current assets",
        "total assets",
        "current liabilities",
        "shareholders equity",
    ),
    "segment": (
        "reportable segment",
        "geography",
        "americas",
        "greater china",
        "product category",
    ),
    "operations": (
        "statements of operations",
        "net sales",
        "revenue",
        "gross margin",
        "operating income",
        "net income",
    ),
}

STRONG_HEADING_PHRASES = (
    "statements of operations",
    "income statements",
    "balance sheets",
    "statements of cash flows",
    "statements of shareholders equity",
)

TERMINAL_ROW_PHRASES = (
    "total assets",
    "total liabilities and shareholders equity",
    "cash cash equivalents and restricted cash and cash equivalents ending balances",
)

CONTINUATION_MARKERS = ("continued", "contd", "续表")


def normalize_stitch_text(value: str) -> str:
    value = value.lower().replace("’", "'")
    return re.sub(r"[^a-z0-9一-鿿%$]+", " ", value).strip()


def _similarity(left: str, right: str) -> float:
    normalized_left = normalize_stitch_text(left)
    normalized_right = normalize_stitch_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def _row_values(row: TableRow) -> list[str]:
    return [
        cell.text.strip()
        for cell in sorted(row.cells, key=lambda cell: cell.column_index)
    ]


def _row_text(row: TableRow) -> str:
    return " | ".join(_row_values(row))


def _rows_similarity(left: TableRow, right: TableRow) -> float:
    left_values = _row_values(left)
    right_values = _row_values(right)
    if not left_values or not right_values:
        return 0.0
    width = max(len(left_values), len(right_values))
    left_values += [""] * (width - len(left_values))
    right_values += [""] * (width - len(right_values))
    return (
        sum(
            _similarity(left_value, right_value)
            for left_value, right_value in zip(left_values, right_values, strict=True)
        )
        / width
    )


def _column_count(table: DocumentTable) -> int:
    rows = [*table.header_rows, *table.body_rows]
    return max((len(row.cells) for row in rows), default=0)


def _column_geometry(table: DocumentTable) -> list[tuple[float, float]]:
    by_column: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for row in [*table.header_rows, *table.body_rows]:
        for cell in row.cells:
            box = cell.bounding_box
            if box.right <= box.left:
                continue
            by_column[cell.column_index].append(
                ((box.left + box.right) / 2, box.right - box.left)
            )
    return [
        (
            median(center for center, _ in by_column[column]),
            median(width for _, width in by_column[column]),
        )
        for column in sorted(by_column)
    ]


def _geometry_similarity(
    previous: DocumentTable,
    following: DocumentTable,
) -> float | None:
    previous_columns = _column_geometry(previous)
    following_columns = _column_geometry(following)
    if not previous_columns or not following_columns:
        return None
    if abs(len(previous_columns) - len(following_columns)) > 1:
        return 0.0

    count = min(len(previous_columns), len(following_columns))
    scores = []
    for index in range(count):
        previous_center, previous_width = previous_columns[index]
        following_center, following_width = following_columns[index]
        center_score = max(0.0, 1.0 - abs(previous_center - following_center) / 0.15)
        width_score = max(0.0, 1.0 - abs(previous_width - following_width) / 0.20)
        scores.append((center_score + width_score) / 2)
    return sum(scores) / len(scores)


def _header_values(table: DocumentTable) -> list[str]:
    if not table.header_rows:
        return []
    column_count = _column_count(table)
    values = []
    for column_index in range(column_count):
        parts = []
        for row in table.header_rows:
            value = next(
                (
                    cell.text.strip()
                    for cell in row.cells
                    if cell.column_index == column_index and cell.text.strip()
                ),
                "",
            )
            if value:
                parts.append(value)
        values.append(" ".join(parts))
    return values


def _header_similarity(
    previous: DocumentTable,
    following: DocumentTable,
) -> float | None:
    previous_headers = _header_values(previous)
    following_headers = _header_values(following)
    if not any(previous_headers) or not any(following_headers):
        return None
    width = max(len(previous_headers), len(following_headers))
    previous_headers += [""] * (width - len(previous_headers))
    following_headers += [""] * (width - len(following_headers))
    return (
        sum(
            _similarity(left, right)
            for left, right in zip(previous_headers, following_headers, strict=True)
        )
        / width
    )


def _cell_type(value: str, first_column: bool = False) -> str:
    normalized = value.strip()
    if not normalized:
        return "empty"
    if first_column and re.search(r"[A-Za-z一-鿿]", normalized):
        return "label"
    if "%" in normalized:
        return "percent"
    if re.search(r"[$€£¥]", normalized):
        return "currency"
    compact = re.sub(r"[(),\s+-]", "", normalized)
    if compact.replace(".", "", 1).isdigit():
        return "number"
    if re.search(r"\b(?:19|20)\d{2}\b", normalized):
        return "date"
    return "text"


def _column_types(table: DocumentTable) -> list[str]:
    column_count = _column_count(table)
    result = []
    for column_index in range(column_count):
        types = []
        for row in table.body_rows[:20]:
            cell = next(
                (cell for cell in row.cells if cell.column_index == column_index),
                None,
            )
            if cell:
                cell_type = _cell_type(cell.text, first_column=column_index == 0)
                if cell_type != "empty":
                    types.append(cell_type)
        result.append(Counter(types).most_common(1)[0][0] if types else "empty")
    return result


def _type_compatibility(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if {left, right} <= {"number", "currency", "percent"}:
        return 0.80
    if "empty" in {left, right}:
        return 0.50
    return 0.0


def _column_type_similarity(
    previous: DocumentTable,
    following: DocumentTable,
) -> float | None:
    previous_types = _column_types(previous)
    following_types = _column_types(following)
    if not previous_types or not following_types:
        return None
    width = max(len(previous_types), len(following_types))
    previous_types += ["empty"] * (width - len(previous_types))
    following_types += ["empty"] * (width - len(following_types))
    return (
        sum(
            _type_compatibility(left, right)
            for left, right in zip(previous_types, following_types, strict=True)
        )
        / width
    )


def _nearby_context(table: DocumentTable, blocks: list[TextBlock]) -> str:
    candidates = [
        block
        for block in blocks
        if block.page_number == table.page_number
        and block.bounding_box.bottom <= table.bounding_box.top
        and table.bounding_box.top - block.bounding_box.bottom <= 0.20
        and len(block.text.strip()) <= 240
    ]
    candidates.sort(key=lambda block: block.bounding_box.bottom)
    parts = [table.title or "", *(block.text for block in candidates[-3:])]
    return " ".join(part.strip() for part in parts if part.strip())


def _table_semantic_text(table: DocumentTable, context: str) -> str:
    first_column = []
    for row in table.body_rows[:30]:
        values = _row_values(row)
        if values:
            first_column.append(values[0])
    return " ".join([context, *first_column])


def _statement_type(text: str) -> str | None:
    normalized = normalize_stitch_text(text)
    scores = {
        category: sum(normalized.count(normalize_stitch_text(term)) for term in terms)
        for category, terms in STATEMENT_KEYWORDS.items()
    }
    best_score = max(scores.values(), default=0)
    if best_score == 0:
        return None
    winners = [category for category, score in scores.items() if score == best_score]
    return winners[0] if len(winners) == 1 else None


def _extract_years(value: str) -> set[str]:
    return set(re.findall(r"\b(?:19|20)\d{2}\b", value))


def _extract_periods(value: str) -> set[str]:
    normalized = normalize_stitch_text(value)
    periods = set()
    for phrase in (
        "three months ended",
        "six months ended",
        "nine months ended",
        "twelve months ended",
        "year ended",
    ):
        if phrase in normalized:
            periods.add(phrase)
    return periods


def _extract_units(value: str) -> set[str]:
    normalized = normalize_stitch_text(value)
    units = set()
    for phrase in ("in millions", "in thousands", "in billions", "per share"):
        if phrase in normalized:
            units.add(phrase)
    for symbol, currency in (("$", "usd"), ("€", "eur"), ("£", "gbp"), ("¥", "yen")):
        if symbol in value:
            units.add(currency)
    return units


def _context_similarity(
    previous: DocumentTable,
    following: DocumentTable,
    previous_context: str,
    following_context: str,
) -> float | None:
    scores = []
    previous_title = previous.title or ""
    following_title = following.title or ""
    if previous_title and following_title:
        scores.append(_similarity(previous_title, following_title))

    for extractor in (_extract_years, _extract_periods, _extract_units):
        previous_values = extractor(
            previous_context + " " + _row_texts(previous.header_rows)
        )
        following_values = extractor(
            following_context + " " + _row_texts(following.header_rows)
        )
        if previous_values and following_values:
            scores.append(
                len(previous_values & following_values)
                / len(previous_values | following_values)
            )
    return sum(scores) / len(scores) if scores else None


def _row_texts(rows: list[TableRow]) -> str:
    return " ".join(_row_text(row) for row in rows)


def _edge_position_score(previous: DocumentTable, following: DocumentTable) -> float:
    return max(
        0.0,
        min(
            1.0, (previous.bounding_box.bottom + (1.0 - following.bounding_box.top)) / 2
        ),
    )


def _contains_marker(value: str, markers: tuple[str, ...]) -> bool:
    normalized = normalize_stitch_text(value).replace(" ", "")
    return any(
        normalize_stitch_text(marker).replace(" ", "") in normalized
        for marker in markers
    )


def _has_strong_new_heading(
    following_context: str,
    previous_type: str | None,
    following_type: str | None,
) -> bool:
    normalized = normalize_stitch_text(following_context)
    has_heading = any(phrase in normalized for phrase in STRONG_HEADING_PHRASES)
    return bool(
        has_heading
        and previous_type
        and following_type
        and previous_type != following_type
    )


def _score_candidate(
    previous: DocumentTable,
    following: DocumentTable,
    blocks: list[TextBlock],
    minimum_score: float,
) -> TableStitchDecision:
    previous_context = _nearby_context(previous, blocks)
    following_context = _nearby_context(following, blocks)
    previous_semantic_text = _table_semantic_text(previous, previous_context)
    following_semantic_text = _table_semantic_text(following, following_context)
    previous_type = _statement_type(previous_semantic_text)
    following_type = _statement_type(following_semantic_text)

    feature_values: dict[str, float | None] = {
        "column_geometry": _geometry_similarity(previous, following),
        "header": _header_similarity(previous, following),
        "context": _context_similarity(
            previous,
            following,
            previous_context,
            following_context,
        ),
        "column_types": _column_type_similarity(previous, following),
        "edge_position": _edge_position_score(previous, following),
        "financial_semantics": (
            1.0
            if previous_type and previous_type == following_type
            else (0.0 if previous_type and following_type else None)
        ),
    }
    available = {
        key: value for key, value in feature_values.items() if value is not None
    }
    weight_total = sum(FEATURE_WEIGHTS[key] for key in available)
    score = (
        sum(FEATURE_WEIGHTS[key] * value for key, value in available.items())
        / weight_total
        if weight_total
        else 0.0
    )

    combined_context = f"{previous_context} {following_context}"
    if _contains_marker(combined_context, CONTINUATION_MARKERS):
        score = min(1.0, score + 0.08)
    if previous.body_rows and _contains_marker(
        _row_text(previous.body_rows[-1]), TERMINAL_ROW_PHRASES
    ):
        score = max(0.0, score - 0.15)

    rejection_reasons = []
    geometry = feature_values["column_geometry"]
    if previous_type and following_type and previous_type != following_type:
        rejection_reasons.append("financial_statement_type_conflict")

    previous_years = _extract_years(
        previous_context + " " + _row_texts(previous.header_rows)
    )
    following_years = _extract_years(
        following_context + " " + _row_texts(following.header_rows)
    )
    if previous_years and following_years and not previous_years & following_years:
        rejection_reasons.append("reporting_year_conflict")

    previous_periods = _extract_periods(previous_context)
    following_periods = _extract_periods(following_context)
    if (
        previous_periods
        and following_periods
        and not previous_periods & following_periods
    ):
        rejection_reasons.append("reporting_period_conflict")

    if abs(_column_count(previous) - _column_count(following)) > 1 and (
        geometry is None or geometry < 0.80
    ):
        rejection_reasons.append("column_structure_conflict")
    if _has_strong_new_heading(
        following_context,
        previous_type,
        following_type,
    ):
        rejection_reasons.append("new_financial_statement_heading")

    strong_signal_count = sum(
        1
        for key in ("column_geometry", "header", "column_types", "context")
        if feature_values[key] is not None and feature_values[key] >= STRONG_SIGNAL_MIN
    )
    if strong_signal_count < 2:
        rejection_reasons.append("insufficient_structural_signals")
    if score < minimum_score:
        rejection_reasons.append("score_below_threshold")

    return TableStitchDecision(
        previous_table_id=previous.id,
        next_table_id=following.id,
        score=round(score, 6),
        matched=not rejection_reasons,
        feature_scores={key: round(value, 6) for key, value in available.items()},
        rejection_reasons=rejection_reasons,
    )


def _copy_row(row: TableRow, table: DocumentTable) -> TableRow:
    copied = row.model_copy(deep=True)
    copied.source_page_number = table.page_number
    copied.source_table_id = table.id
    return copied


def _is_generic_title(title: str | None, table_id: str) -> bool:
    if not title:
        return True
    normalized = normalize_stitch_text(title).replace(" ", "")
    return normalized in {
        normalize_stitch_text(table_id).replace(" ", ""),
        "continued",
        "contd",
        "续表",
    }


def _logical_table_id(tables: list[DocumentTable]) -> str:
    if len(tables) == 1:
        return tables[0].id
    raw_id = "|".join(table.id for table in tables)
    return f"logical_{uuid5(NAMESPACE_URL, raw_id).hex[:16]}"


def _merge_chain(
    tables: list[DocumentTable],
    edge_scores: dict[tuple[str, str], float],
) -> LogicalTable:
    canonical_headers = next(
        (
            [_copy_row(row, table) for row in table.header_rows]
            for table in tables
            if table.header_rows
        ),
        [],
    )
    body_rows: list[TableRow] = []
    for table in tables:
        rows = [_copy_row(row, table) for row in table.body_rows]
        if rows and canonical_headers:
            if _rows_similarity(rows[0], canonical_headers[-1]) >= REPEATED_HEADER_MIN:
                rows.pop(0)
        if body_rows and rows:
            if _rows_similarity(body_rows[-1], rows[0]) >= REPEATED_BOUNDARY_ROW_MIN:
                rows.pop(0)
        body_rows.extend(rows)

    title = next(
        (
            table.title
            for table in tables
            if not _is_generic_title(table.title, table.id)
        ),
        tables[0].title,
    )
    source_processors = sorted(
        {source for table in tables for source in table.source_processors}
    )
    source_refs = list(
        dict.fromkeys(source for table in tables for source in table.source_refs)
    )
    selected_scores = [
        edge_scores[(previous.id, following.id)]
        for previous, following in zip(tables, tables[1:])
    ]
    return LogicalTable(
        id=_logical_table_id(tables),
        title=title,
        page_start=tables[0].page_number,
        page_end=tables[-1].page_number,
        header_rows=canonical_headers,
        body_rows=body_rows,
        segments=[
            TableSegmentRef(
                table_id=table.id,
                page_number=table.page_number,
                bounding_box=table.bounding_box.model_copy(deep=True),
            )
            for table in tables
        ],
        source_table_ids=[table.id for table in tables],
        stitch_confidence=min(selected_scores) if selected_scores else 1.0,
        source_processors=source_processors,
        source_refs=source_refs,
    )


def build_singleton_stitching_result(
    tables: list[DocumentTable],
    warnings: list[str] | None = None,
) -> TableStitchingResult:
    ordered = sorted(
        tables,
        key=lambda table: (
            table.page_number,
            table.bounding_box.top,
            table.bounding_box.left,
            table.id,
        ),
    )
    logical_tables = [_merge_chain([table], {}) for table in ordered]
    return TableStitchingResult(
        logical_tables=logical_tables,
        physical_table_count=len(tables),
        logical_table_count=len(logical_tables),
        stitched_table_count=0,
        warnings=list(warnings or []),
    )


def stitch_tables(
    tables: list[DocumentTable],
    blocks: list[TextBlock],
    minimum_score: float = 0.75,
    enabled: bool = True,
) -> TableStitchingResult:
    if not enabled or not tables:
        return build_singleton_stitching_result(tables)

    tables_by_page: dict[int, list[DocumentTable]] = defaultdict(list)
    for table in tables:
        tables_by_page[table.page_number].append(table)

    decisions = []
    decision_by_edge = {}
    for page_number in sorted(tables_by_page):
        previous_tables = [
            table
            for table in tables_by_page[page_number]
            if table.bounding_box.bottom >= BOTTOM_EDGE_MIN
        ]
        following_tables = [
            table
            for table in tables_by_page.get(page_number + 1, [])
            if table.bounding_box.top <= TOP_EDGE_MAX
        ]
        for previous in previous_tables:
            for following in following_tables:
                decision = _score_candidate(
                    previous,
                    following,
                    blocks,
                    minimum_score,
                )
                decisions.append(decision)
                decision_by_edge[(previous.id, following.id)] = decision

    eligible = sorted(
        (decision for decision in decisions if decision.matched),
        key=lambda decision: (
            -decision.score,
            decision.previous_table_id,
            decision.next_table_id,
        ),
    )
    outgoing = {}
    incoming = {}
    edge_scores = {}
    for decision in eligible:
        if decision.previous_table_id in outgoing or decision.next_table_id in incoming:
            decision.matched = False
            decision.rejection_reasons.append("conflicting_higher_score_edge")
            continue
        outgoing[decision.previous_table_id] = decision.next_table_id
        incoming[decision.next_table_id] = decision.previous_table_id
        edge_scores[(decision.previous_table_id, decision.next_table_id)] = (
            decision.score
        )

    table_by_id = {table.id: table for table in tables}
    roots = [table for table in tables if table.id not in incoming]
    roots.sort(
        key=lambda table: (
            table.page_number,
            table.bounding_box.top,
            table.bounding_box.left,
            table.id,
        )
    )
    logical_tables = []
    visited = set()
    for root in roots:
        chain = []
        current = root
        while current.id not in visited:
            chain.append(current)
            visited.add(current.id)
            next_id = outgoing.get(current.id)
            if not next_id:
                break
            current = table_by_id[next_id]
        logical_tables.append(_merge_chain(chain, edge_scores))

    for table in tables:
        if table.id not in visited:
            logical_tables.append(_merge_chain([table], edge_scores))

    return TableStitchingResult(
        logical_tables=logical_tables,
        decisions=sorted(
            decisions,
            key=lambda decision: (
                decision.previous_table_id,
                decision.next_table_id,
            ),
        ),
        physical_table_count=len(tables),
        logical_table_count=len(logical_tables),
        stitched_table_count=sum(
            1 for table in logical_tables if len(table.source_table_ids) > 1
        ),
    )


def stitch_tables_fail_open(
    tables: list[DocumentTable],
    blocks: list[TextBlock],
    minimum_score: float = 0.75,
    enabled: bool = True,
) -> TableStitchingResult:
    try:
        return stitch_tables(
            tables=tables,
            blocks=blocks,
            minimum_score=minimum_score,
            enabled=enabled,
        )
    except Exception as exc:
        return build_singleton_stitching_result(
            tables,
            warnings=[
                f"table stitching fell back to physical tables: "
                f"{exc.__class__.__name__}: {str(exc)[:300]}"
            ],
        )
