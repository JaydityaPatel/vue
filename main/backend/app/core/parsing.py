"""PDF/text extraction and PII scrubbing before candidate content reaches models."""
from io import BytesIO
import logging
from pathlib import Path
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger("vue.parsing")
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_DOCUMENT_CHARS = 100_000
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s().-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?:\s*(?:x|ext\.?)\s*\d{1,6})?(?!\w)", re.IGNORECASE)


class DocumentParsingError(ValueError):
    """An upload is unreadable, empty, unsupported, or exceeds safe limits."""


def _check_bytes(data: bytes) -> None:
    if not data:
        raise DocumentParsingError("The uploaded document is empty.")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise DocumentParsingError("Documents must be 10 MB or smaller.")


def _usable(text: str, label: str) -> str:
    cleaned = "\n".join(line.strip() for line in text.replace("\x00", "").splitlines() if line.strip())
    if not cleaned:
        raise DocumentParsingError(f"No readable text was found in the {label}. Scanned PDFs without a text layer are not supported.")
    if len(cleaned) > MAX_DOCUMENT_CHARS:
        raise DocumentParsingError(f"The {label} contains too much text. Keep it under {MAX_DOCUMENT_CHARS:,} characters.")
    return cleaned


def parse_resume(file_bytes: bytes, filename: str) -> str:
    """Extract a PDF text layer with pypdf; OCR is intentionally unsupported."""
    _check_bytes(file_bytes)
    if Path(filename).suffix.casefold() != ".pdf" or not file_bytes.startswith(b"%PDF-"):
        raise DocumentParsingError("Upload a valid PDF resume.")
    try:
        reader = PdfReader(BytesIO(file_bytes), strict=True)
        if reader.is_encrypted:
            raise DocumentParsingError("The resume PDF is password protected. Upload an unlocked PDF.")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except DocumentParsingError:
        raise
    except (PdfReadError, ValueError, OSError, EOFError, KeyError, IndexError) as exc:
        raise DocumentParsingError("The resume PDF is damaged or could not be read.") from exc
    return _usable(text, "resume PDF")


def _parse_jd_file(file_bytes: bytes, filename: str) -> str:
    _check_bytes(file_bytes)
    suffix = Path(filename).suffix.casefold()
    if suffix == ".txt":
        try:
            return _usable(file_bytes.decode("utf-8-sig"), "job description")
        except UnicodeDecodeError as exc:
            raise DocumentParsingError("The job description .txt file must use UTF-8 encoding.") from exc
    if suffix == ".pdf" and file_bytes.startswith(b"%PDF-"):
        try:
            reader = PdfReader(BytesIO(file_bytes), strict=True)
            if reader.is_encrypted:
                raise DocumentParsingError("The job description PDF is password protected.")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except DocumentParsingError:
            raise
        except (PdfReadError, ValueError, OSError, EOFError, KeyError, IndexError) as exc:
            raise DocumentParsingError("The job description PDF is damaged or could not be read.") from exc
        return _usable(text, "job description PDF")
    raise DocumentParsingError("Job descriptions must be a PDF or UTF-8 .txt file.")


def parse_job_description(file_bytes: bytes | None, text: str | None, filename: str | None = None) -> str:
    """Prefer nonblank pasted text over a file; otherwise extract the file."""
    if text is not None and text.strip():
        return _usable(text, "pasted job description")
    if file_bytes is not None:
        return _parse_jd_file(file_bytes, filename or "job-description.pdf")
    raise DocumentParsingError("Add a job description by pasting text or uploading a PDF/.txt file.")


def redact_contact_details(text: str) -> tuple[str, dict[str, int]]:
    """Replace email/phone values, logging counts only; preserve names and prose."""
    scrubbed, emails = _EMAIL.subn("[email redacted]", text)
    scrubbed, phones = _PHONE.subn("[phone redacted]", scrubbed)
    counts = {"emails": emails, "phones": phones}
    if emails or phones:
        logger.info("candidate_contact_redacted email_count=%d phone_count=%d", emails, phones)
    return scrubbed, counts


def summarize_candidate_context(text: str, max_chars: int = 2400) -> str:
    """Deterministic extractive fallback: keep evidence-rich lines, never log them."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(text) <= max_chars:
        return text
    evidence = re.compile(r"\b(project|built|led|designed|implemented|experience|result|impact|reduced|increased|owned|responsib|skill|education|requirement|qualification|years?|team|kafka|react|python|sql|cloud)\b", re.I)
    ranked = sorted(enumerate(lines), key=lambda pair: (len(evidence.findall(pair[1])) + 2 * bool(re.search(r"\d", pair[1])), -pair[0]), reverse=True)
    selected: set[int] = set()
    used = 0
    for index, line in ranked:
        if used + len(line) + 1 > max_chars:
            continue
        selected.add(index)
        used += len(line) + 1
    summary = "\n".join(line for index, line in enumerate(lines) if index in selected)
    return summary or text[:max_chars]
