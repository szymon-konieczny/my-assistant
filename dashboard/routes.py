import logging
import threading
from calendar import monthrange

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import db
from config import settings
from models import TriggerRequest, TriggerResponse
from invoice.scanner import run_scan, cancel_scan
from gmail.auth import get_auth_url, handle_oauth_callback, is_account_connected
from ksef.client import query_invoices as ksef_query_invoices, KsefRateLimitError
from news.fetcher import fetch_all_feeds

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="dashboard/templates")


# --- Dashboard ---

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = request.session.get("user", {})
    return templates.TemplateResponse("index.html", {"request": request, "user": user, "active_page": "invoices"})


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


# --- KSeF API ---

@router.get("/api/ksef/invoices")
async def ksef_invoices(month: str | None = None):
    """Fetch invoices from KSeF API for a given month (YYYY-MM)."""
    if not month:
        from invoice.scanner import get_previous_month_range
        date_from, date_to = get_previous_month_range()
    else:
        parts = month.split("-")
        year, mon = int(parts[0]), int(parts[1])
        last_day = monthrange(year, mon)[1]
        date_from = f"{year}-{mon:02d}-01"
        date_to = f"{year}-{mon:02d}-{last_day}"

    try:
        invoices = ksef_query_invoices(date_from, date_to)
        return {"invoices": invoices}
    except KsefRateLimitError:
        return {"invoices": [], "error": "Rate limit exceeded. Try again in a few minutes."}
    except Exception as e:
        logger.error(f"KSeF query failed: {e}")
        return {"invoices": [], "error": "Failed to fetch from KSeF. Please try again later."}


# --- News ---

@router.get("/news", response_class=HTMLResponse)
async def news_page(request: Request):
    user = request.session.get("user", {})
    return templates.TemplateResponse("news.html", {"request": request, "user": user, "active_page": "news"})


@router.get("/api/news")
async def list_news(category_id: int | None = None, limit: int = 50):
    return {"articles": db.get_news_articles(category_id=category_id, limit=limit)}


@router.get("/api/news/categories")
async def list_news_categories():
    return {"categories": db.get_news_categories()}


class NewsCategoryRequest(BaseModel):
    name: str
    feeds: list[dict]  # [{"name": "...", "feed_url": "..."}]


@router.post("/api/news/categories")
async def create_news_category(body: NewsCategoryRequest):
    cat_id = db.add_news_category(body.name, body.feeds)
    return {"id": cat_id, "name": body.name}


@router.delete("/api/news/categories/{category_id}")
async def remove_news_category(category_id: int):
    db.delete_news_category(category_id)
    return {"deleted": True}


@router.post("/api/news/fetch")
async def trigger_news_fetch():
    thread = threading.Thread(target=fetch_all_feeds, daemon=True)
    thread.start()
    return {"status": "started"}


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


@router.post("/api/runs/cancel")
async def cancel_running_scan():
    cancelled = cancel_scan()
    return {"cancelled": cancelled}


@router.get("/api/status")
async def status():
    runs = db.get_scan_runs(limit=1)
    last_run = runs[0] if runs else None
    return {
        "status": "ok",
        "last_run": last_run,
    }
