from dataclasses import dataclass, field
from dotenv import load_dotenv
import os

load_dotenv()


@dataclass
class GmailAccount:
    alias: str
    email: str
    token_path: str


@dataclass
class Settings:
    anthropic_api_key: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    ksef_token: str = field(
        default_factory=lambda: os.getenv("KSEF_TOKEN", "")
    )
    gmail_credentials_file: str = field(
        default_factory=lambda: os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
    )
    accounting_email: str = field(
        default_factory=lambda: os.getenv("ACCOUNTING_EMAIL", "biuro@silesia-tax.pl")
    )
    excluded_senders: list[str] = field(
        default_factory=lambda: [
            s.strip()
            for s in os.getenv("EXCLUDED_SENDERS", "biuro@silesia-tax.pl").split(",")
        ]
    )
    data_dir: str = field(
        default_factory=lambda: os.getenv("DATA_DIR", ".")
    )
    invoice_storage_dir: str = field(
        default_factory=lambda: os.getenv("INVOICE_STORAGE_DIR", "invoices")
    )
    database_path: str = field(
        default_factory=lambda: os.getenv("DATABASE_PATH", "invoices.db")
    )
    claude_model: str = field(
        default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
    )
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    base_url: str = field(
        default_factory=lambda: os.getenv("BASE_URL", "http://localhost:8000")
    )
    scan_cron_day: int = field(
        default_factory=lambda: int(os.getenv("SCAN_CRON_DAY", "5"))
    )
    scan_cron_hour: int = field(
        default_factory=lambda: int(os.getenv("SCAN_CRON_HOUR", "9"))
    )
    scan_cron_minute: int = field(
        default_factory=lambda: int(os.getenv("SCAN_CRON_MINUTE", "0"))
    )

    @property
    def oauth_redirect_uri(self) -> str:
        return f"{self.base_url}/oauth/callback"

    @property
    def gmail_accounts(self) -> list[GmailAccount]:
        raw = os.getenv("GMAIL_ACCOUNTS", "")
        if not raw:
            return []
        email_map = {
            "szykon": "szykon@gmail.com",
            "progrise": "simon@progrise.dev",
        }
        data_dir = os.getenv("DATA_DIR", ".")
        accounts = []
        for alias in raw.split(","):
            alias = alias.strip()
            accounts.append(
                GmailAccount(
                    alias=alias,
                    email=email_map.get(alias, f"{alias}@gmail.com"),
                    token_path=os.path.join(data_dir, "tokens", f"{alias}.json"),
                )
            )
        return accounts


settings = Settings()
