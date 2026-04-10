import base64
import logging
import threading
import uuid
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from config import settings
from gmail.auth import get_credentials
from gmail.client import GmailClient, build_invoice_query
from invoice.parser import extract_invoice_data
from invoice.filters import is_polish_invoice, is_excluded_sender
from invoice.storage import save_invoice_pdf
import db

logger = logging.getLogger(__name__)

_cancel_event: threading.Event | None = None
_current_run_id: str | None = None

POLISH_MONTHS = {
    1: "styczeń", 2: "luty", 3: "marzec", 4: "kwiecień",
    5: "maj", 6: "czerwiec", 7: "lipiec", 8: "sierpień",
    9: "wrzesień", 10: "październik", 11: "listopad", 12: "grudzień",
}


def get_previous_month_range() -> tuple[str, str]:
    """Return (first_day, last_day) of the previous month as YYYY-MM-DD."""
    today = date.today()
    first_of_this_month = today.replace(day=1)
    last_of_prev = first_of_this_month - timedelta(days=1)
    first_of_prev = last_of_prev.replace(day=1)
    return first_of_prev.isoformat(), last_of_prev.isoformat()


def cancel_scan():
    """Cancel the currently running scan."""
    global _cancel_event, _current_run_id
    if _cancel_event and _current_run_id:
        logger.info(f"Cancelling scan {_current_run_id}")
        _cancel_event.set()
        db.update_scan_run(
            _current_run_id,
            completed_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            status="cancelled",
        )
        return True
    return False


def run_scan(
    after_date: str | None = None,
    before_date: str | None = None,
) -> str:
    """Run a full invoice scan across all Gmail accounts.
    Returns the scan run ID.
    """
    global _cancel_event, _current_run_id

    if not after_date or not before_date:
        after_date, before_date = get_previous_month_range()

    run_id = str(uuid.uuid4())[:8]
    _cancel_event = threading.Event()
    _current_run_id = run_id
    db.create_scan_run(run_id, after_date, before_date)
    logger.info(f"Scan {run_id}: scanning {after_date} to {before_date}")

    total_found = 0
    total_polish = 0
    collected_invoices: list[dict] = []

    try:
        for account in settings.gmail_accounts:
            if _cancel_event.is_set():
                logger.info(f"Scan {run_id}: cancelled")
                break

            logger.info(f"Scan {run_id}: checking account {account.email}")
            try:
                creds = get_credentials(account)
                if not creds:
                    logger.warning(f"  Account {account.email} not connected, skipping")
                    continue
                client = GmailClient(creds)
                found, polish, invoices = _scan_account(
                    client, account.alias, after_date, before_date, run_id,
                    _cancel_event,
                )
                total_found += found
                total_polish += polish
                collected_invoices.extend(invoices)
            except Exception as e:
                logger.error(f"Error scanning {account.email}: {e}")

        if _cancel_event.is_set():
            # Status already updated by cancel_scan()
            return run_id

        # Create draft to accountant if we have non-Polish invoices
        draft_created = False
        if collected_invoices:
            try:
                draft_created = _create_accountant_draft(
                    after_date, before_date, collected_invoices
                )
            except Exception as e:
                logger.error(f"Error creating draft: {e}")

        db.update_scan_run(
            run_id,
            completed_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            status="completed",
            invoices_found=total_found,
            invoices_polish_skipped=total_polish,
            draft_created=draft_created,
        )
        logger.info(
            f"Scan {run_id}: completed. Found={total_found}, Polish={total_polish}, Draft={draft_created}"
        )

    except Exception as e:
        logger.error(f"Scan {run_id} failed: {e}")
        db.update_scan_run(
            run_id,
            status="failed",
            error_message=str(e),
            invoices_found=total_found,
            invoices_polish_skipped=total_polish,
        )
    finally:
        _cancel_event = None
        _current_run_id = None

    return run_id


def _scan_account(
    client: GmailClient,
    account_alias: str,
    after_date: str,
    before_date: str,
    run_id: str,
    cancel_event: threading.Event,
) -> tuple[int, int, list[dict]]:
    """Scan a single Gmail account. Returns (found, polish_skipped, invoice_list)."""
    # Gmail query dates use YYYY/MM/DD format
    # Extend search window by 10 days to catch invoices sent in early next month
    # (e.g. Google Payments sends March invoice on ~April 2)
    gmail_after = after_date.replace("-", "/")
    extended_before = date.fromisoformat(before_date) + timedelta(days=10)
    gmail_before = extended_before.isoformat().replace("-", "/")
    query = build_invoice_query(gmail_after, gmail_before)

    messages = client.search_messages(query)
    logger.info(f"  Found {len(messages)} matching emails in {account_alias}")

    found = 0
    polish = 0
    invoices = []

    for msg_ref in messages:
        if cancel_event.is_set():
            break
        message = client.get_message(msg_ref["id"])
        sender = client.get_sender_email(message)

        if is_excluded_sender(sender):
            continue

        subject = client.get_header(message, "Subject") or ""
        email_date = client.get_header(message, "Date") or ""
        attachments = client.get_pdf_attachments(message)

        for att in attachments:
            try:
                # Download PDF
                if "data" in att:
                    pdf_bytes = base64.urlsafe_b64decode(att["data"])
                else:
                    pdf_bytes = client.download_attachment(
                        msg_ref["id"], att["attachment_id"]
                    )

                # Extract data with Claude
                data = extract_invoice_data(pdf_bytes)
                found += 1

                # Filter Polish invoices
                if is_polish_invoice(data):
                    polish += 1
                    logger.info(f"  Skipping Polish invoice: {att['filename']}")
                    continue

                # Deduplicate by invoice number (cross-account)
                if data.invoice_number and db.invoice_number_exists(data.invoice_number):
                    logger.info(f"  Skipping duplicate invoice: {data.invoice_number}")
                    continue

                # Save PDF
                pdf_path = save_invoice_pdf(
                    pdf_bytes, data.sell_date, data.vendor_name, att["filename"]
                )

                # Store in database
                db.insert_invoice(
                    gmail_message_id=msg_ref["id"],
                    gmail_account=account_alias,
                    attachment_filename=att["filename"],
                    vendor_name=data.vendor_name,
                    invoice_number=data.invoice_number,
                    sell_date=data.sell_date,
                    amount=data.amount,
                    currency=data.currency,
                    sender_email=sender,
                    email_subject=subject,
                    email_date=email_date,
                    pdf_path=pdf_path,
                    scan_run_id=run_id,
                )

                invoices.append(
                    {
                        "vendor_name": data.vendor_name,
                        "invoice_number": data.invoice_number,
                        "amount": data.amount,
                        "currency": data.currency,
                        "pdf_path": pdf_path,
                        "pdf_bytes": pdf_bytes,
                        "filename": att["filename"],
                    }
                )

            except Exception as e:
                logger.error(f"  Error processing {att['filename']}: {e}")

    return found, polish, invoices


def _create_accountant_draft(
    after_date: str,
    before_date: str,
    invoices: list[dict],
) -> bool:
    """Create a Gmail draft to the accounting partner with invoice attachments."""
    # Use the first account to create the draft
    if not settings.gmail_accounts:
        return False

    account = settings.gmail_accounts[0]
    creds = get_credentials(account)
    client = GmailClient(creds)

    # Parse month for Polish subject
    parts = after_date.split("-")
    year = parts[0]
    month_num = int(parts[1])
    month_name = POLISH_MONTHS.get(month_num, str(month_num))

    subject = f"Dokumenty - {month_name} {year}"

    body = (
        f"Dzień dobry\n"
        f"\n"
        f"W załączeniu przesyłam dokumenty za {month_name}.\n"
        f"\n"
        f"Pozdrawiam serdecznie,\n"
        f"Szymon Konieczny\n"
        f"tel.: +48 731 905 527"
    )

    # Prepare attachments (deduplicate by invoice number)
    seen = set()
    pdf_files = []
    for inv in invoices:
        if "pdf_bytes" not in inv:
            continue
        inv_num = inv.get("invoice_number")
        if inv_num and inv_num in seen:
            continue
        if inv_num:
            seen.add(inv_num)
        pdf_files.append((inv.get("filename", "invoice.pdf"), inv["pdf_bytes"]))

    client.create_draft(
        to=settings.accounting_email,
        subject=subject,
        body_text=body,
        pdf_files=pdf_files,
    )
    return True
