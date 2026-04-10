import json
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from config import settings, GmailAccount

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]


def _build_client_config() -> dict:
    """Build OAuth client config from env vars or credentials file."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    if client_id and client_secret:
        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.oauth_redirect_uri],
            }
        }

    if os.path.exists(settings.gmail_credentials_file):
        with open(settings.gmail_credentials_file) as f:
            return json.load(f)

    raise FileNotFoundError(
        "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET env vars, "
        "or provide a credentials.json file"
    )


def _create_flow() -> Flow:
    """Create an OAuth flow from env vars or credentials file."""
    config = _build_client_config()
    return Flow.from_client_config(config, scopes=SCOPES, redirect_uri=settings.oauth_redirect_uri)


def get_credentials(account: GmailAccount) -> Credentials | None:
    """Load existing OAuth2 credentials for a Gmail account.
    Returns None if not authenticated yet (user must go through web OAuth).
    """
    token_path = account.token_path
    if not os.path.exists(token_path):
        return None

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_credentials(account, creds)
        else:
            return None

    return creds


def get_auth_url(account_alias: str) -> str:
    """Generate the OAuth2 authorization URL for a Gmail account."""
    flow = _create_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=account_alias,
    )
    return auth_url


def handle_oauth_callback(code: str, account_alias: str) -> GmailAccount | None:
    """Exchange the OAuth2 authorization code for credentials."""
    account = _find_account(account_alias)
    if not account:
        return None

    flow = _create_flow()
    flow.fetch_token(code=code)
    _save_credentials(account, flow.credentials)
    return account


def is_account_connected(account: GmailAccount) -> bool:
    """Check if an account has valid credentials."""
    return get_credentials(account) is not None


def _save_credentials(account: GmailAccount, creds: Credentials):
    """Save credentials to the token file."""
    os.makedirs(os.path.dirname(account.token_path), exist_ok=True)
    with open(account.token_path, "w") as f:
        f.write(creds.to_json())


def _find_account(alias: str) -> GmailAccount | None:
    """Find a Gmail account by alias."""
    for account in settings.gmail_accounts:
        if account.alias == alias:
            return account
    return None
