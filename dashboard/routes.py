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
from digest.engine import generate_digest

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
async def list_news(category_id: int | None = None, date: str | None = None, per_category: int = 5):
    return {"articles": db.get_news_articles(category_id=category_id, date=date, per_category=per_category)}


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


@router.get("/api/news/{article_id}/detail")
async def get_article_detail(article_id: int):
    """Get article with extended summary, generating it on first access."""
    article = db.get_news_article(article_id)
    if not article:
        return {"error": "Article not found"}

    if article.get("extended_summary"):
        return {"article": article}

    # Generate extended summary from the source page
    if not article.get("source_url"):
        return {"article": article}

    import anthropic
    import requests as http_requests
    try:
        resp = http_requests.get(article["source_url"], timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        # Extract text roughly — strip HTML tags
        import re
        text = re.sub(r"<script[^>]*>.*?</script>", "", resp.text, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()[:5000]

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": (
                f"Article title: {article['title']}\n"
                f"Source: {article['source_name']}\n\n"
                f"Page content:\n{text}\n\n"
                "Napisz szczegółowe podsumowanie tego artykułu w 3-5 akapitach po polsku. "
                "Opisz kluczowe fakty, kontekst i dlaczego to jest ważne. Bądź rzeczowy i zwięzły."
            )}],
        )
        extended = response.content[0].text
        db.update_news_article_summary(article_id, extended)
        article["extended_summary"] = extended
    except Exception as e:
        logger.error(f"Article detail generation failed: {e}")

    return {"article": article}


@router.post("/api/news/fetch")
async def trigger_news_fetch():
    thread = threading.Thread(target=fetch_all_feeds, daemon=True)
    thread.start()
    return {"status": "started"}


@router.post("/api/news/summarize")
async def summarize_news(category_id: int | None = None):
    """Summarize current news articles using Claude."""
    articles = db.get_news_articles(category_id=category_id, limit=30)
    if not articles:
        return {"summary": "No articles to summarize."}

    import anthropic
    article_text = "\n".join(
        f"- [{a['source_name']}] {a['title']}: {a.get('summary', '') or ''}"
        for a in articles
    )
    prompt = (
        "You are a news analyst. Below are today's news articles. "
        "Napisz zwięzłe podsumowanie po polsku, podkreślając najważniejsze wydarzenia, "
        "kluczowe trendy i praktyczne wnioski. Pogrupuj tematycznie. Użyj punktów. "
        "Maksymalnie 500 słów.\n\n" + article_text
    )
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"summary": response.content[0].text}
    except Exception as e:
        logger.error(f"News summary failed: {e}")
        return {"summary": "Failed to generate summary. Please try again."}


# --- Email Digest ---

@router.get("/digest", response_class=HTMLResponse)
async def digest_page(request: Request):
    user = request.session.get("user", {})
    return templates.TemplateResponse("digest.html", {"request": request, "user": user, "active_page": "digest"})


@router.get("/api/digest")
async def get_digest_api(date: str | None = None):
    if not date:
        from datetime import date as dt_date, timedelta
        date = (dt_date.today() - timedelta(days=1)).isoformat()
    digest = db.get_digest(date)
    dates = db.get_digest_dates()
    return {"digest": digest, "available_dates": dates, "requested_date": date}


@router.post("/api/digest/generate")
async def trigger_digest(date: str | None = None):
    thread = threading.Thread(target=generate_digest, kwargs={"target_date": date}, daemon=True)
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
