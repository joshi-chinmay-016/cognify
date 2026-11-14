"""Unit tests for Google Drive integration module."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.config import AppConfig
from app.drive.authentication import (
    CredentialsNotFoundError,
    get_drive_credentials,
)
from app.drive.drive_client import DriveItem, GoogleDriveClient


def test_missing_credentials_raises_error(tmp_path: Path):
    """Test that missing credentials.json raises CredentialsNotFoundError."""
    cred_file = tmp_path / "nonexistent_credentials.json"
    token_file = tmp_path / "token.json"

    with pytest.raises(CredentialsNotFoundError):
        get_drive_credentials(cred_file, token_file, ["https://www.googleapis.com/auth/drive.readonly"])


def test_drive_item_type_detection():
    """Test DriveItem correctly detects file types from name or mime type."""
    docx_item = DriveItem(
        file_id="123",
        name="Quarterly_Report.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        modified_time="2026-01-01T00:00:00Z",
    )
    assert docx_item.file_type == "docx"

    xlsx_item = DriveItem(
        file_id="456",
        name="sales_2025.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        modified_time="2026-01-01T00:00:00Z",
    )
    assert xlsx_item.file_type == "xlsx"


def test_drive_client_unauthenticated_actions(tmp_path: Path):
    """Test DriveClient safely handles unauthenticated calls."""
    cfg = AppConfig(
        google_drive_folder_id="mock_folder",
        google_credentials_file=tmp_path / "none.json",
        google_token_file=tmp_path / "none_token.json",
    )
    client = GoogleDriveClient(cfg)
    assert not client.is_authenticated

    # Listing should return empty list gracefully without throwing
    files = client.list_folder_files()
    assert files == []

    # Sync should report error gracefully
    report = client.sync(download_dir=tmp_path / "downloads")
    assert len(report.errors) > 0


@patch("app.drive.drive_client.build")
def test_drive_client_sync_logic(mock_build, tmp_path: Path):
    """Test synchronization logic: new, modified, unchanged, and deleted items."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)

    # Existing file on disk
    existing_file = download_dir / "sales_2025.xlsx"
    existing_file.write_text("dummy")

    cfg = AppConfig(
        google_drive_folder_id="test_folder",
        downloads_dir=download_dir,
    )
    client = GoogleDriveClient(cfg)
    client.service = MagicMock()
    client._is_authenticated = True

    # Mock list_folder_files
    client.list_folder_files = MagicMock(return_value=[
        DriveItem(
            file_id="f1",
            name="sales_2025.xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            modified_time="2026-01-01T00:00:00Z",
        ),
        DriveItem(
            file_id="f2",
            name="new_doc.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            modified_time="2026-01-02T00:00:00Z",
        ),
    ])

    # Mock download_file
    client.download_file = MagicMock(side_effect=lambda fid, path, **kwargs: path.write_text("downloaded"))

    known_manifest = {
        "f1": "2026-01-01T00:00:00Z",  # unchanged
        "f_old": "2025-01-01T00:00:00Z", # deleted remotely
    }

    report = client.sync(download_dir=download_dir, known_manifest=known_manifest)

    assert len(report.unchanged) == 1
    assert report.unchanged[0].name == "sales_2025.xlsx"
    assert len(report.downloaded) == 1
    assert report.downloaded[0].name == "new_doc.docx"
    assert "f_old" in report.deleted

