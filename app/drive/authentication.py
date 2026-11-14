"""Google Drive OAuth 2.0 Desktop Authentication Module.

Handles local token caching, token refreshes, and interactive authorization flow.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)


class DriveAuthError(Exception):
    """Base exception for Google Drive authentication errors."""


class CredentialsNotFoundError(DriveAuthError):
    """Raised when the client secrets credentials.json file is missing."""


class AuthenticationFailedError(DriveAuthError):
    """Raised when OAuth authorization fails."""


def get_drive_credentials(
    credentials_file: Path,
    token_file: Path,
    scopes: Sequence[str],
    interactive: bool = True,
) -> Credentials | None:
    """Retrieve or generate valid Google Drive OAuth 2.0 credentials.

    Args:
        credentials_file: Path to client secret JSON file downloaded from Google Cloud.
        token_file: Path to locally persisted token JSON file.
        scopes: OAuth scopes required (e.g., https://www.googleapis.com/auth/drive.readonly).
        interactive: Whether to prompt local browser for authorization if token is missing.

    Returns:
        Valid google.oauth2.credentials.Credentials, or None if authentication failed
        or credentials file is absent.

    Raises:
        CredentialsNotFoundError: If credentials_file does not exist.
        AuthenticationFailedError: If token exchange fails.
    """
    creds: Credentials | None = None

    # Load existing cached token if present
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), scopes)
            logger.info("Loaded cached Google Drive OAuth token from %s", token_file)
        except Exception as e:
            logger.warning("Failed to load existing token from %s: %s", token_file, e)
            creds = None

    # Validate or refresh token
    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            logger.info("Refreshing expired Google Drive OAuth token...")
            creds.refresh(Request())
            token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(token_file, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            logger.info("Refreshed Google Drive token saved to %s", token_file)
            return creds
        except Exception as e:
            logger.warning("Token refresh failed: %s. Initiating re-authentication.", e)
            creds = None

    # Credentials file must exist to initiate new OAuth flow
    if not credentials_file.exists():
        msg = (
            f"Google Drive client credentials file not found at: '{credentials_file}'.\n"
            "Please create an OAuth 2.0 Desktop Application credential in Google Cloud Console,\n"
            "download the JSON file, and save it as 'credentials.json' in the project root."
        )
        logger.warning(msg)
        raise CredentialsNotFoundError(msg)

    if not interactive:
        logger.warning("Authentication required but interactive flow disabled.")
        return None

    # Run local OAuth server flow
    try:
        logger.info("Starting local OAuth 2.0 authorization flow...")
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), scopes)
        creds = flow.run_local_server(port=0, open_browser=True)

        token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        logger.info("OAuth credentials obtained and stored at %s", token_file)
        return creds
    except Exception as e:
        msg = f"OAuth 2.0 authorization flow failed: {e}"
        logger.error(msg)
        raise AuthenticationFailedError(msg) from e
