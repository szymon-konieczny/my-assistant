import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import db
from dashboard.routes import router
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
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    from config import settings

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
