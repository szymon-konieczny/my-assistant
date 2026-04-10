import os
from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request
from starlette.responses import RedirectResponse, HTMLResponse
from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

from config import settings

templates = Jinja2Templates(directory="dashboard/templates")

oauth = OAuth()

oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

auth_router = APIRouter()


@auth_router.get("/auth/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@auth_router.get("/auth/google")
async def login_google(request: Request):
    redirect_uri = f"{settings.base_url}/auth/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@auth_router.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")
    if not user_info:
        return RedirectResponse("/?error=auth_failed")

    email = user_info.get("email", "").lower()
    if email not in settings.allowed_emails:
        return RedirectResponse("/?error=unauthorized")

    request.session["user"] = {
        "email": email,
        "name": user_info.get("name", email),
    }
    return RedirectResponse("/")


@auth_router.get("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/auth/login")


def get_current_user(request: Request) -> dict | None:
    return request.session.get("user")


def require_auth(request: Request) -> bool:
    """Check if the request is authenticated. Returns True if OK."""
    # Allow auth routes and static files without auth
    path = request.url.path
    if path.startswith("/auth/") or path.startswith("/static/"):
        return True
    return get_current_user(request) is not None
