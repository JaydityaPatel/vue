from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject, DictionaryObject, NameObject,
)

from app.core.parsing import (
    DocumentParsingError, parse_job_description, parse_resume, redact_contact_details,
)


def pdf_with_text(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    content = DecodedStreamObject()
    content.set_data(("BT /F1 12 Tf 72 700 Td (" + text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj ET").encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_extracts_text_layer_from_pdf_resume():
    text = parse_resume(pdf_with_text("Jane Candidate built Kafka systems"), "resume.pdf")
    assert text == "Jane Candidate built Kafka systems"


def test_scanned_or_textless_pdf_returns_clear_no_ocr_error():
    with pytest.raises(DocumentParsingError, match="Scanned PDFs without a text layer"):
        parse_resume(pdf_with_text(""), "scan.pdf")


@pytest.mark.parametrize("data,filename", [(b"not pdf", "resume.pdf"), (b"%PDF-broken", "resume.pdf"), (b"%PDF-ok", "resume.txt"), (b"", "resume.pdf")])
def test_invalid_resume_file_is_a_parsing_error(data, filename):
    with pytest.raises(DocumentParsingError):
        parse_resume(data, filename)


def test_redaction_counts_only_and_preserves_name_and_resume_evidence(caplog):
    text = "Jane Candidate; jane@example.com; +1 (415) 555-2671; built Kafka event processing"
    scrubbed, counts = redact_contact_details(text)
    assert counts == {"emails": 1, "phones": 1}
    assert "Jane Candidate" in scrubbed and "built Kafka event processing" in scrubbed
    assert "jane@example.com" not in scrubbed and "555-2671" not in scrubbed
    assert "jane@example.com" not in caplog.text and "555-2671" not in caplog.text
    assert "email_count=1 phone_count=1" in caplog.text


def test_job_description_text_takes_precedence_over_file():
    assert parse_job_description(b"broken file", "Pasted role requirements", "broken.pdf") == "Pasted role requirements"


def test_job_description_accepts_uploaded_pdf_and_utf8_text_file():
    assert parse_job_description(pdf_with_text("Build APIs for healthcare"), None, "role.pdf") == "Build APIs for healthcare"
    assert parse_job_description("Build accessible products".encode(), None, "role.txt") == "Build accessible products"


@pytest.mark.parametrize("kwargs", [
    {"file_bytes": None, "text": None}, {"file_bytes": b"bad", "text": ""},
    {"file_bytes": b"", "text": ""}, {"file_bytes": b"not PDF", "text": None},
])
def test_empty_or_malformed_job_description_is_clear(kwargs):
    with pytest.raises(DocumentParsingError):
        parse_job_description(**kwargs)
