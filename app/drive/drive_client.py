"""Google Drive Client module for Cognify.

Manages folder listing, file discovery, downloading, and timestamp-based synchronization.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from app.config import AppConfig
from app.drive.authentication import (
    CredentialsNotFoundError,
    DriveAuthError,
    get_drive_credentials,
)

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".docx", ".xlsx", ".xls", ".pdf"}
SUPPORTED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
    "application/pdf": "pdf",
    "application/vnd.google-apps.document": "docx",
    "application/vnd.google-apps.spreadsheet": "xlsx",
}


@dataclass
class DriveItem:
    """Represents a file discovered on Google Drive."""

    file_id: str
    name: str
    mime_type: str
    modified_time: str
    size: int = 0
    file_type: str = ""

    def __post_init__(self) -> None:
        if not self.file_type:
            suffix = Path(self.name).suffix.lower()
            if suffix in SUPPORTED_EXTENSIONS:
                self.file_type = suffix.lstrip(".")
            elif self.mime_type in SUPPORTED_MIME_TYPES:
                self.file_type = SUPPORTED_MIME_TYPES[self.mime_type]


@dataclass
class SyncReport:
    """Summary of Google Drive folder synchronization."""

    total_remote: int = 0
    downloaded: list[Path] = field(default_factory=list)
    modified: list[Path] = field(default_factory=list)
    unchanged: list[Path] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class GoogleDriveClient:
    """Client for Google Drive API interactions."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.service: Resource | None = None
        self._is_authenticated = False

    def authenticate(self, interactive: bool = True) -> bool:
        """Authenticate with Google Drive using configured credentials."""
        try:
            creds = get_drive_credentials(
                credentials_file=self.config.google_credentials_file,
                token_file=self.config.google_token_file,
                scopes=self.config.google_scopes,
                interactive=interactive,
            )
            if creds:
                self.service = build("drive", "v3", credentials=creds, cache_discovery=False)
                self._is_authenticated = True
                logger.info("Successfully connected to Google Drive API.")
                return True
        except CredentialsNotFoundError as e:
            logger.warning("Google Drive credentials not found: %s", e)
        except DriveAuthError as e:
            logger.error("Google Drive authentication failed: %s", e)
        except Exception as e:
            logger.error("Unexpected error during Google Drive authentication: %s", e)

        self.service = None
        self._is_authenticated = False
        return False

    @property
    def is_authenticated(self) -> bool:
        return self._is_authenticated and self.service is not None

    def list_folder_files(self, folder_id: str | None = None) -> list[DriveItem]:
        """List supported documents in the specified Google Drive folder.

        Args:
            folder_id: Optional folder ID. Defaults to config.google_drive_folder_id.

        Returns:
            List of DriveItem instances.
        """
        if not self.service:
            logger.warning("Google Drive client is not authenticated.")
            return []

        target_folder = folder_id or self.config.google_drive_folder_id
        if not target_folder:
            logger.warning("No Google Drive folder ID configured.")
            return []

        query = f"'{target_folder}' in parents and trashed = false"
        items: list[DriveItem] = []
        page_token: str | None = None

        try:
            while True:
                response = (
                    self.service.files()
                    .list(
                        q=query,
                        spaces="drive",
                        fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
                        pageToken=page_token,
                        pageSize=100,
                    )
                    .execute()
                )

                for file_obj in response.get("files", []):
                    name = file_obj.get("name", "")
                    suffix = Path(name).suffix.lower()
                    mime_type = file_obj.get("mimeType", "")

                    # Filter only supported document and spreadsheet types
                    if suffix in SUPPORTED_EXTENSIONS or mime_type in SUPPORTED_MIME_TYPES:
                        item = DriveItem(
                            file_id=file_obj["id"],
                            name=name,
                            mime_type=mime_type,
                            modified_time=file_obj.get("modifiedTime", ""),
                            size=int(file_obj.get("size", 0)),
                        )
                        items.append(item)

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            logger.info("Discovered %d supported files in Drive folder '%s'.", len(items), target_folder)
            return items

        except HttpError as e:
            logger.error("Google Drive API error listing folder '%s': %s", target_folder, e)
            return []
        except Exception as e:
            logger.error("Failed to list files from Google Drive: %s", e)
            return []

    def download_file(self, file_id: str, destination_path: Path, mime_type: str = "") -> Path:
        """Download binary file from Google Drive to local disk."""
        if not self.service:
            raise RuntimeError("Google Drive client is not authenticated.")

        destination_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if Google Docs or Google Sheets export is required
        if mime_type == "application/vnd.google-apps.document":
            request = self.service.files().export_media(
                fileId=file_id,
                mimeType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        elif mime_type == "application/vnd.google-apps.spreadsheet":
            request = self.service.files().export_media(
                fileId=file_id,
                mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            request = self.service.files().get_media(fileId=file_id)

        with open(destination_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request, chunksize=1024 * 1024)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug("Downloading file %s: %d%%", file_id, int(status.progress() * 100))

        logger.info("Successfully downloaded Drive file %s to %s", file_id, destination_path)
        return destination_path

    def sync(
        self,
        folder_id: str | None = None,
        download_dir: Path | None = None,
        known_manifest: dict[str, str] | None = None,
    ) -> SyncReport:
        """Synchronize remote Drive folder with local download directory.

        Args:
            folder_id: Folder ID to sync. Defaults to configured folder ID.
            download_dir: Directory where files should be stored.
            known_manifest: Dict of file_id -> last_known_modified_time for change detection.

        Returns:
            SyncReport detailing downloaded, modified, unchanged, and deleted items.
        """
        report = SyncReport()
        if not self.service:
            report.errors.append("Google Drive client is not authenticated.")
            return report

        target_dir = download_dir or self.config.downloads_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        manifest = known_manifest or {}

        remote_items = self.list_folder_files(folder_id)
        report.total_remote = len(remote_items)

        remote_ids = {item.file_id for item in remote_items}

        for item in remote_items:
            dest_name = item.name
            if not Path(dest_name).suffix and item.file_type:
                dest_name = f"{dest_name}.{item.file_type}"
            dest_file = target_dir / dest_name
            last_known_mod = manifest.get(item.file_id)

            # Check if file needs download: new, modified timestamp, or missing on disk
            needs_download = False
            if not dest_file.exists():
                needs_download = True
            elif last_known_mod != item.modified_time:
                needs_download = True

            if needs_download:
                try:
                    self.download_file(item.file_id, dest_file, mime_type=item.mime_type)
                    if last_known_mod is not None:
                        report.modified.append(dest_file)
                    else:
                        report.downloaded.append(dest_file)
                except Exception as e:
                    err_msg = f"Failed to download {item.name} ({item.file_id}): {e}"
                    logger.error(err_msg)
                    report.errors.append(err_msg)
            else:
                report.unchanged.append(dest_file)

        # Detect files that existed locally or in manifest but are no longer in remote folder
        for file_id in manifest:
            if file_id not in remote_ids:
                report.deleted.append(file_id)

        logger.info(
            "Sync complete. Downloaded: %d, Modified: %d, Unchanged: %d, Deleted: %d, Errors: %d",
            len(report.downloaded),
            len(report.modified),
            len(report.unchanged),
            len(report.deleted),
            len(report.errors),
        )
        return report

