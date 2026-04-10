from pydantic import BaseModel
from datetime import date, datetime


class ExtractedInvoiceData(BaseModel):
    vendor_name: str | None = None
    invoice_number: str | None = None
    sell_date: str | None = None  # YYYY-MM-DD
    amount: float | None = None
    currency: str | None = None
    is_polish: bool = False
    language: str | None = None


class InvoiceRecord(BaseModel):
    id: int
    gmail_message_id: str
    gmail_account: str
    attachment_filename: str
    vendor_name: str | None
    invoice_number: str | None
    sell_date: str | None
    amount: float | None
    currency: str | None
    sender_email: str | None
    email_subject: str | None
    email_date: str | None
    pdf_path: str | None
    scan_run_id: str | None
    created_at: str | None


class MonthlyTotal(BaseModel):
    month: str
    currency: str
    total: float
    count: int


class CurrencyTotal(BaseModel):
    currency: str
    total: float
    count: int


class ScanRunRecord(BaseModel):
    id: str
    started_at: str
    completed_at: str | None
    status: str
    invoices_found: int
    invoices_polish_skipped: int
    draft_created: bool
    error_message: str | None
    date_range_start: str | None
    date_range_end: str | None


class TriggerRequest(BaseModel):
    after_date: str | None = None  # YYYY-MM-DD
    before_date: str | None = None  # YYYY-MM-DD


class TriggerResponse(BaseModel):
    run_id: str
    status: str
    message: str
