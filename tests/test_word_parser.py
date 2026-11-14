"""Unit tests for Word document parser."""

from pathlib import Path
import docx
import pytest

from app.ingestion.word_parser import WordParser


def create_sample_docx(path: Path) -> Path:
    """Helper to create a well-formed test docx file."""
    doc = docx.Document()
    doc.core_properties.title = "Company Policy"
    doc.core_properties.author = "HR Department"

    doc.add_heading("Leave Policy and Benefits", level=1)
    doc.add_paragraph("Employees are eligible for 20 days of paid annual leave.")

    doc.add_heading("Health Insurance Coverage", level=2)
    doc.add_paragraph("Comprehensive health coverage begins on the first day of employment.")

    # Add a table
    table = doc.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "Benefit Tier"
    table.cell(0, 1).text = "Coverage Amount"
    table.cell(1, 0).text = "Standard"
    table.cell(1, 1).text = "$50,000"
    table.cell(2, 0).text = "Premium"
    table.cell(2, 1).text = "$100,000"

    doc.save(str(path))
    return path


def test_word_parser_extracts_headings_paragraphs_and_tables(tmp_path: Path):
    """Test standard Word document parsing with all structural elements."""
    docx_file = tmp_path / "company_policy.docx"
    create_sample_docx(docx_file)

    parsed = WordParser.parse(docx_file, file_id="doc_101", filename="company_policy.docx")

    assert not parsed.is_empty
    assert parsed.filename == "company_policy.docx"
    assert parsed.file_id == "doc_101"
    assert parsed.title == "Company Policy"
    assert parsed.author == "HR Department"

    # Check headings and paragraphs
    assert "Leave Policy and Benefits" in parsed.full_text
    assert "Employees are eligible for 20 days" in parsed.full_text
    assert "Health Insurance Coverage" in parsed.full_text

    # Check table content
    assert "Benefit Tier" in parsed.full_text
    assert "Premium" in parsed.full_text
    assert "$100,000" in parsed.full_text

    # Check sections breakdown
    heading_sections = [s for s in parsed.sections if s.section_type == "heading"]
    table_sections = [s for s in parsed.sections if s.section_type == "table"]
    assert len(heading_sections) >= 2
    assert len(table_sections) == 1


def test_word_parser_handles_nonexistent_and_empty_files(tmp_path: Path):
    """Test graceful handling of nonexistent and corrupted files."""
    missing_file = tmp_path / "ghost.docx"
    parsed_missing = WordParser.parse(missing_file)
    assert parsed_missing.is_empty
    assert "not found" in parsed_missing.metadata["error"].lower()

    corrupt_file = tmp_path / "corrupt.docx"
    corrupt_file.write_bytes(b"not a valid zip/docx content")
    parsed_corrupt = WordParser.parse(corrupt_file)
    assert parsed_corrupt.is_empty
    assert "package" in parsed_corrupt.metadata["error"].lower() or "error" in parsed_corrupt.metadata
