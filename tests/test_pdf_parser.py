"""Unit tests for PDF document parser."""

from pathlib import Path
import pypdf
import pytest

from app.ingestion.pdf_parser import PDFParser


def create_sample_pdf(path: Path) -> Path:
    """Helper to create a simple PDF with test text."""
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    # In pypdf, we can write an annotation or create simple page
    # Alternatively write a minimal valid PDF format:
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length 44 >> stream\n"
        b"BT /F1 12 Tf 100 700 Td (Cognify Test PDF Content) Tj ET\n"
        b"endstream\nendobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000266 00000 n \n0000000360 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n441\n%%EOF"
    )
    path.write_bytes(pdf_content)
    return path


def test_pdf_parser_extracts_text(tmp_path: Path):
    """Test extracting text from a valid PDF."""
    pdf_file = tmp_path / "sample.pdf"
    create_sample_pdf(pdf_file)

    parsed = PDFParser.parse(pdf_file, file_id="pdf_1", filename="sample.pdf")
    assert not parsed.is_empty
    assert parsed.filename == "sample.pdf"
    assert parsed.page_count == 1
    assert "Cognify Test PDF Content" in parsed.full_text


def test_pdf_parser_corrupted_file(tmp_path: Path):
    """Test graceful handling of a corrupted PDF."""
    bad_pdf = tmp_path / "corrupt.pdf"
    bad_pdf.write_bytes(b"not a valid pdf data")

    parsed = PDFParser.parse(bad_pdf)
    assert parsed.is_empty
    assert "error" in parsed.metadata
