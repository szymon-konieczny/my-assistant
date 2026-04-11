import base64
import email.utils
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


class GmailClient:
    def __init__(self, credentials: Credentials):
        self.service = build("gmail", "v1", credentials=credentials)

    def search_messages(self, query: str) -> list[dict]:
        """Search for messages matching the query. Returns list of {id, threadId}."""
        messages = []
        request = self.service.users().messages().list(userId="me", q=query)
        while request:
            response = request.execute()
            if "messages" in response:
                messages.extend(response["messages"])
            request = self.service.users().messages().list_next(request, response)
        return messages

    def get_message(self, message_id: str) -> dict:
        """Get full message details including headers and payload."""
        return (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

    def get_header(self, message: dict, name: str) -> str | None:
        """Extract a header value from a message."""
        headers = message.get("payload", {}).get("headers", [])
        for h in headers:
            if h["name"].lower() == name.lower():
                return h["value"]
        return None

    def get_sender_email(self, message: dict) -> str | None:
        """Extract sender email from the From header."""
        from_header = self.get_header(message, "From")
        if not from_header:
            return None
        _, addr = email.utils.parseaddr(from_header)
        return addr.lower()

    def get_pdf_attachments(self, message: dict) -> list[dict]:
        """Get PDF attachment metadata from a message.
        Returns list of {filename, attachment_id, size}.
        """
        attachments = []
        payload = message.get("payload", {})
        self._collect_pdf_parts(payload, message["id"], attachments)
        return attachments

    def _collect_pdf_parts(self, part: dict, message_id: str, result: list):
        """Recursively find PDF parts in MIME structure."""
        filename = part.get("filename", "")
        mime_type = part.get("mimeType", "")

        if filename.lower().endswith(".pdf") or mime_type == "application/pdf":
            body = part.get("body", {})
            attachment_id = body.get("attachmentId")
            if attachment_id:
                result.append(
                    {
                        "filename": filename or "attachment.pdf",
                        "attachment_id": attachment_id,
                        "size": body.get("size", 0),
                    }
                )
            elif body.get("data"):
                result.append(
                    {
                        "filename": filename or "attachment.pdf",
                        "data": body["data"],
                        "size": body.get("size", 0),
                    }
                )

        for sub_part in part.get("parts", []):
            self._collect_pdf_parts(sub_part, message_id, result)

    def get_body_text(self, message: dict) -> str:
        """Extract plain text body from a message's MIME structure."""
        payload = message.get("payload", {})
        parts = []
        self._collect_text_parts(payload, parts)
        return "\n".join(parts).strip()

    def _collect_text_parts(self, part: dict, result: list):
        """Recursively find text/plain parts in MIME structure."""
        mime_type = part.get("mimeType", "")
        body = part.get("body", {})

        if mime_type == "text/plain" and body.get("data"):
            decoded = base64.urlsafe_b64decode(body["data"]).decode("utf-8", errors="replace")
            result.append(decoded)

        for sub_part in part.get("parts", []):
            self._collect_text_parts(sub_part, result)

    def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download an attachment by ID and return raw bytes."""
        response = (
            self.service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
        data = response["data"]
        return base64.urlsafe_b64decode(data)

    def create_draft(
        self,
        to: str,
        subject: str,
        body_text: str,
        pdf_files: list[tuple[str, bytes]],
    ) -> str:
        """Create a Gmail draft with PDF attachments.
        pdf_files: list of (filename, pdf_bytes) tuples.
        Returns the draft ID.
        """
        msg = MIMEMultipart()
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        for filename, pdf_bytes in pdf_files:
            attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
            attachment.add_header(
                "Content-Disposition", "attachment", filename=filename
            )
            msg.attach(attachment)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        draft = (
            self.service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw}})
            .execute()
        )
        return draft["id"]


def build_invoice_query(after_date: str, before_date: str) -> str:
    """Build Gmail search query for invoice emails with PDF attachments.
    Dates should be in YYYY/MM/DD format.
    """
    subject_terms = (
        "(subject:invoice OR subject:faktura OR subject:receipt "
        "OR subject:Rechnung OR subject:facture OR subject:factura "
        "OR from:payments-noreply@google.com)"
    )
    date_filter = f"after:{after_date} before:{before_date}"
    attachment_filter = "has:attachment"
    exclusion = "-from:biuro@silesia-tax.pl"

    return f"{subject_terms} {date_filter} {attachment_filter} {exclusion}"
