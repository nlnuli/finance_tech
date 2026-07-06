from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from io import BytesIO

from google.api_core import exceptions as google_exceptions
from google.api_core.client_options import ClientOptions
from google.cloud import documentai_v1
from pypdf import PdfReader, PdfWriter


ONLINE_REQUEST_MAX_BYTES = 40 * 1024 * 1024
RETRYABLE_ERRORS = (
    google_exceptions.DeadlineExceeded,
    google_exceptions.ResourceExhausted,
    google_exceptions.ServiceUnavailable,
    google_exceptions.TooManyRequests,
)


class PdfBatchTooLargeError(ValueError):
    pass


@dataclass(frozen=True)
class PdfBatch:
    content: bytes
    start_page: int
    end_page: int

    @property
    def page_count(self) -> int:
        return self.end_page - self.start_page + 1


@dataclass
class ProcessorCallResult:
    document: object
    processor_id: str
    processor_name: str
    attempts: int
    duration_seconds: float


def _open_pdf(content: bytes) -> PdfReader:
    reader = PdfReader(BytesIO(content))
    if reader.is_encrypted:
        try:
            decrypted = reader.decrypt("")
        except Exception as exc:
            raise ValueError("Encrypted PDF files are not supported.") from exc
        if not decrypted:
            raise ValueError("Encrypted PDF files are not supported.")
    return reader


def get_pdf_page_count(content: bytes) -> int:
    reader = _open_pdf(content)
    return len(reader.pages)


def _render_pdf_pages(reader: PdfReader, start: int, end: int) -> bytes:
    writer = PdfWriter()
    for page_index in range(start, end):
        writer.add_page(reader.pages[page_index])
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def split_pdf_batches(
    content: bytes,
    page_batch_size: int,
    max_batch_bytes: int = ONLINE_REQUEST_MAX_BYTES,
) -> list[PdfBatch]:
    reader = _open_pdf(content)
    total_pages = len(reader.pages)
    batches: list[PdfBatch] = []

    def append_span(start: int, end: int) -> None:
        batch_content = _render_pdf_pages(reader, start, end)
        if len(batch_content) <= max_batch_bytes:
            batches.append(
                PdfBatch(
                    content=batch_content,
                    start_page=start + 1,
                    end_page=end,
                )
            )
            return

        if end - start <= 1:
            raise PdfBatchTooLargeError(
                f"PDF page {start + 1} exceeds the online processing limit."
            )

        midpoint = start + (end - start) // 2
        append_span(start, midpoint)
        append_span(midpoint, end)

    for start in range(0, total_pages, page_batch_size):
        append_span(start, min(start + page_batch_size, total_pages))

    return batches


class DocumentAIClient:
    def __init__(
        self,
        project_id: str,
        location: str,
        call_timeout_seconds: float,
        retry_attempts: int = 3,
        client=None,
    ):
        self.project_id = project_id
        self.location = location
        self.call_timeout_seconds = call_timeout_seconds
        self.retry_attempts = max(1, retry_attempts)
        self._client = client

    @property
    def client(self):
        if self._client is None:
            endpoint = f"{self.location}-documentai.googleapis.com"
            self._client = documentai_v1.DocumentProcessorServiceAsyncClient(
                client_options=ClientOptions(api_endpoint=endpoint)
            )
        return self._client

    def processor_name(self, processor_id: str) -> str:
        return (
            f"projects/{self.project_id}/locations/{self.location}/"
            f"processors/{processor_id}"
        )

    async def process(
        self,
        processor_id: str,
        content: bytes,
        mime_type: str = "application/pdf",
    ) -> ProcessorCallResult:
        name = self.processor_name(processor_id)
        request = documentai_v1.ProcessRequest(
            name=name,
            raw_document=documentai_v1.RawDocument(
                content=content,
                mime_type=mime_type,
            ),
        )
        started_at = time.perf_counter()
        last_error: Exception | None = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = await self.client.process_document(
                    request=request,
                    timeout=self.call_timeout_seconds,
                )
                return ProcessorCallResult(
                    document=response.document,
                    processor_id=processor_id,
                    processor_name=name,
                    attempts=attempt,
                    duration_seconds=time.perf_counter() - started_at,
                )
            except RETRYABLE_ERRORS as exc:
                last_error = exc
                if attempt >= self.retry_attempts:
                    break
                await asyncio.sleep(min(2 ** (attempt - 1), 5))

        assert last_error is not None
        raise last_error
