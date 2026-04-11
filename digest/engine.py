import json
import logging
from datetime import date, timedelta

import anthropic

import db
from config import settings
from gmail.auth import get_credentials
from gmail.client import GmailClient

logger = logging.getLogger(__name__)

DIGEST_PROMPT = """You are an email digest assistant. Analyze the emails below and create a structured daily digest.

Categorize each email into one of these sections:
- **action_items**: Emails requiring a response, decision, or task from me
- **important**: Significant updates, notifications, or information I should know about
- **fyi**: Newsletters, promotional emails, automated notifications — low priority

For each email, provide:
- sender: who sent it
- subject: the email subject
- summary: 1-2 sentence summary of the content
- urgency: "high", "medium", or "low"

Return ONLY valid JSON in this format:
{
  "action_items": [{"sender": "...", "subject": "...", "summary": "...", "urgency": "high"}],
  "important": [{"sender": "...", "subject": "...", "summary": "...", "urgency": "medium"}],
  "fyi": [{"sender": "...", "subject": "...", "summary": "...", "urgency": "low"}]
}

Skip spam, delivery notifications, and purely automated system emails. If no emails fit a category, use an empty array.

Here are the emails:
"""


def _truncate(text: str, max_len: int = 1000) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def generate_digest(target_date: str | None = None) -> dict | None:
    """Generate email digest for all accounts for the given date.

    Args:
        target_date: YYYY-MM-DD (defaults to yesterday)

    Returns the digest content dict or None on failure.
    """
    if not target_date:
        yesterday = date.today() - timedelta(days=1)
        target_date = yesterday.isoformat()

    # Collect emails from all accounts
    all_emails = []

    for account in settings.gmail_accounts:
        creds = get_credentials(account)
        if not creds:
            logger.warning(f"Digest: account {account.email} not connected, skipping")
            continue

        client = GmailClient(creds)

        # Gmail date query format
        gmail_date = target_date.replace("-", "/")
        next_day = (date.fromisoformat(target_date) + timedelta(days=1)).isoformat().replace("-", "/")
        query = f"after:{gmail_date} before:{next_day}"

        messages = client.search_messages(query)
        logger.info(f"Digest: {len(messages)} emails from {account.email} on {target_date}")

        for msg_ref in messages[:50]:  # Cap at 50 per account
            message = client.get_message(msg_ref["id"])
            sender = client.get_sender_email(message) or ""
            subject = client.get_header(message, "Subject") or "(no subject)"
            body = _truncate(client.get_body_text(message))

            all_emails.append({
                "from": sender,
                "subject": subject,
                "body": body,
                "account": account.alias,
            })

    if not all_emails:
        logger.info(f"Digest: no emails found for {target_date}")
        content = json.dumps({"action_items": [], "important": [], "fyi": []})
        db.save_digest("all", target_date, content, 0)
        return json.loads(content)

    # Build prompt with all emails
    email_text = ""
    for i, em in enumerate(all_emails, 1):
        email_text += f"\n--- Email {i} ---\nFrom: {em['from']}\nSubject: {em['subject']}\nBody: {em['body']}\n"

    # Single Claude call for all emails
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=4096,
            messages=[{"role": "user", "content": DIGEST_PROMPT + email_text}],
        )
        raw = response.content[0].text.strip()

        # Parse JSON from response (handle markdown code blocks)
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        content = json.loads(raw)
    except Exception as e:
        logger.error(f"Digest: Claude summarization failed: {e}")
        return None

    db.save_digest("all", target_date, json.dumps(content), len(all_emails))
    logger.info(
        f"Digest for {target_date}: {len(all_emails)} emails -> "
        f"{len(content.get('action_items', []))} actions, "
        f"{len(content.get('important', []))} important, "
        f"{len(content.get('fyi', []))} FYI"
    )
    return content
