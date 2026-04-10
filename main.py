import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import db
from config import settings
from dashboard.routes import router
from dashboard.auth import auth_router, require_auth
from scheduler.jobs import scheduler, setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    setup_scheduler()
    scheduler.start()
    logging.getLogger(__name__).info("Invoice Assistant started")
    yield
    scheduler.shutdown()


app = FastAPI(title="Invoice Assistant", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not require_auth(request):
        return RedirectResponse("/auth/login")
    return await call_next(request)


app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")
app.include_router(auth_router)
app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
