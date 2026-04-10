import threading
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import db
from config import settings
from models import TriggerRequest, TriggerResponse
from invoice.scanner import run_scan
from gmail.auth import get_auth_url, handle_oauth_callback, is_account_connected

router = APIRouter()
templates = Jinja2Templates(directory="dashboard/templates")


# --- Dashboard ---

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# --- OAuth ---

@router.get("/oauth/connect/{account_alias}")
async def oauth_connect(account_alias: str):
    """Start OAuth flow for a Gmail account."""
    auth_url = get_auth_url(account_alias)
    return RedirectResponse(auth_url)


@router.get("/oauth/callback")
async def oauth_callback(code: str, state: str):
    """Handle OAuth callback from Google."""
    account = handle_oauth_callback(code, state)
    if account:
        return RedirectResponse(f"/?connected={account.alias}")
    return RedirectResponse("/?error=oauth_failed")


@router.get("/api/accounts")
async def list_accounts():
    """List Gmail accounts and their connection status."""
    accounts = []
    for acc in settings.gmail_accounts:
        accounts.append({
            "alias": acc.alias,
            "email": acc.email,
            "connected": is_account_connected(acc),
        })
    return {"accounts": accounts}


# --- Invoices API ---

@router.get("/api/invoices")
async def list_invoices(month: str | None = None, page: int = 1, per_page: int = 50):
    invoices = db.get_invoices(month=month, page=page, per_page=per_page)
    return {"invoices": invoices, "page": page, "per_page": per_page}


@router.get("/api/invoices/totals")
async def monthly_totals():
    return {"totals": db.get_monthly_totals()}


@router.get("/api/invoices/grand-total")
async def grand_total():
    return {"totals": db.get_grand_totals()}


# --- Scan Runs API ---

@router.get("/api/runs")
async def list_runs():
    return {"runs": db.get_scan_runs()}


@router.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    run = db.get_scan_run(run_id)
    if not run:
        return {"error": "Run not found"}, 404
    invoices = db.get_invoices_for_run(run_id)
    return {"run": run, "invoices": invoices}


@router.post("/api/runs/trigger")
async def trigger_scan(body: TriggerRequest | None = None):
    after_date = body.after_date if body else None
    before_date = body.before_date if body else None

    thread = threading.Thread(
        target=run_scan,
        kwargs={"after_date": after_date, "before_date": before_date},
        daemon=True,
    )
    thread.start()

    return TriggerResponse(
        run_id="pending",
        status="started",
        message="Scan started in background. Check /api/runs for status.",
    )


@router.get("/api/status")
async def status():
    runs = db.get_scan_runs(limit=1)
    last_run = runs[0] if runs else None
    return {
        "status": "ok",
        "last_run": last_run,
    }
