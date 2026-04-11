import email.utils
import logging
import re

import db
from config import settings
from gmail.auth import get_credentials
from gmail.client import GmailClient

logger = logging.getLogger(__name__)


def _extract_unsubscribe_url(header_value: str) -> str | None:
    """Extract HTTP URL from List-Unsubscribe header (RFC 2369)."""
    urls = re.findall(r'<(https?://[^>]+)>', header_value)
    return urls[0] if urls else None


def scan_newsletters() -> int:
    """Scan Gmail for emails with List-Unsubscribe headers.
    Returns count of unique senders found.
    """
    total = 0

    for account in settings.gmail_accounts:
        creds = get_credentials(account)
        if not creds:
            continue

        client = GmailClient(creds)
        # Search for recent emails with unsubscribe headers (last 90 days)
        messages = client.search_messages("newer_than:90d list:unsubscribe")
        logger.info(f"Newsletter scan: {len(messages)} messages from {account.email}")

        for msg_ref in messages[:200]:  # Cap to avoid overload
            message = client.get_message(msg_ref["id"])
            unsub_header = client.get_header(message, "List-Unsubscribe")
            if not unsub_header:
                continue

            sender_email = client.get_sender_email(message)
            if not sender_email:
                continue

            from_header = client.get_header(message, "From") or ""
            sender_name, _ = email.utils.parseaddr(from_header)

            unsub_url = _extract_unsubscribe_url(unsub_header)
            date_header = client.get_header(message, "Date") or ""

            db.upsert_newsletter(
                sender_email=sender_email,
                sender_name=sender_name or None,
                unsubscribe_url=unsub_url,
                last_seen=date_header,
            )
            total += 1

    logger.info(f"Newsletter scan complete: {total} entries processed")
    return total
